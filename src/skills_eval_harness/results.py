"""Parse Harbor v0.21 jobs and derive fail-closed run summaries."""
from __future__ import annotations

import json
import math
import re
import shlex
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from harbor.models.job.result import JobResult, TrialResult
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .hashing import atomic_write_json, sha256_file
from .acceptance import CURRENT_ACCEPTANCE_POLICY, DIMENSIONS, METRICS
from .models import AnalysisPlan
from .judge import (
    Evidence,
    EvidenceKind,
    JudgeVerdict,
)

if TYPE_CHECKING:
    from .summary import SummaryV6


EVIDENCE_KINDS: dict[str, EvidenceKind] = {
    "oracle": "oracle",
    "workspace": "workspace",
    "mechanical": "telemetry",
    "postconditions": "oracle",
    "fallback_attestation": "telemetry",
    "stdout": "telemetry",
    "stderr": "telemetry",
}
INVALID_REASONS = {
    "harbor_process_failed",
    "secret_exposure_redacted",
    "harbor_or_verifier_validation_failed",
    "trial_exception",
    "deterministic_verifier_failed",
    "judge_validation_failed",
    "equivalent_evidence_judge_inconsistency",
}


class JudgeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role: Literal["system", "user"]
    content: str = Field(min_length=1)


class CellRecord(BaseModel):
    """Strict terminal record for one planned arm/scenario/sample identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=True)
    arm: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    sample: int = Field(ge=1)
    valid: bool
    pass_: bool = Field(alias="pass")
    required_pass: bool
    scenario_outcome: Literal["passed", "failed"] = "passed"
    scenario_failures: list[str] = Field(default_factory=list)
    invalid_reason: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)
    wall_time_seconds: float | None = Field(default=None, ge=0)
    n_input_tokens: int | None = Field(default=None, ge=0)
    n_cache_tokens: int | None = Field(default=None, ge=0)
    n_output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    evidence: list[Evidence] = Field(default_factory=list)
    judge_messages: list[JudgeMessage] = Field(default_factory=list)
    verdict: JudgeVerdict | None = None


    @field_validator("scores")
    @classmethod
    def validate_scores(cls, scores: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(value) or not 0 <= value <= 5 for value in scores.values()):
            raise ValueError("scores must be finite values in [0, 5]")
        return scores

    @model_validator(mode="after")
    def terminal_contract(self) -> "CellRecord":
        if not set(self.scores).issubset(DIMENSIONS):
            raise ValueError("cell contains unknown score dimensions")
        if self.valid:
            if (self.scenario_outcome == "failed") != bool(self.scenario_failures):
                raise ValueError("scenario failures must be present exactly for failed scenario outcomes")
            if self.scenario_outcome == "failed" and self.pass_:
                raise ValueError("failed scenario outcomes cannot pass overall")
            required = (
                bool(self.scores)
                and self.invalid_reason is None
                and self.wall_time_seconds is not None
                and self.n_input_tokens is not None
                and self.n_cache_tokens is not None
                and self.n_output_tokens is not None
                and self.cost_usd is not None
                and bool(self.evidence)
                and len(self.judge_messages) == 2
                and self.verdict is not None
            )
            if not required:
                raise ValueError("valid cell omits scores, metrics, judge inputs, or verdict")
        elif self.pass_ or self.required_pass or self.invalid_reason not in INVALID_REASONS or self.scores:
            raise ValueError("invalid cell must be terminal, failing, reasoned, and unscored")
        return self


def load_job(job_dir: Path) -> JobResult:
    job = JobResult.model_validate_json((job_dir / "result.json").read_text(encoding="utf-8"))
    trials = [TrialResult.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted(job_dir.glob("*/result.json"))]
    return job.model_copy(update={"trial_results": trials})


def validate_job(
    job_dir: Path,
    *,
    expected_trials: int,
    require_mechanical_success: bool = True,
    allow_failed_trials: bool = False,
) -> JobResult:
    lock = json.loads((job_dir / "lock.json").read_text(encoding="utf-8"))
    if lock.get("schema_version") != 3 or lock.get("harbor") != {"version": "0.21.0", "is_editable": False}:
        raise ValueError("invalid or unexpected Harbor lock")
    if len(lock.get("trials", [])) != expected_trials:
        raise ValueError("incomplete Harbor lock")
    job = load_job(job_dir)
    if job.n_total_trials != expected_trials or len(job.trial_results) != expected_trials:
        raise ValueError("incomplete Harbor job")
    if job.finished_at is None or (
        not allow_failed_trials and (job.stats.n_errored_trials or job.stats.n_cancelled_trials)
    ):
        raise ValueError("Harbor job contains failed, cancelled, or unfinished trials")
    for trial in job.trial_results:
        if trial.exception_info is not None:
            if allow_failed_trials:
                continue
            raise ValueError(f"trial {trial.trial_name} failed")
        if trial.verifier_environment_mode != "separate":
            raise ValueError(f"trial {trial.trial_name} did not use a separate verifier sandbox")
        rewards = trial.verifier_result.rewards if trial.verifier_result else None
        if require_mechanical_success and (not rewards or rewards.get("infrastructure") != 1):
            raise ValueError(f"trial {trial.trial_name} failed deterministic verification")
    return job


def trial_mechanical_success(trial: TrialResult) -> bool:
    rewards = trial.verifier_result.rewards if trial.verifier_result else None
    return trial.exception_info is None and bool(rewards and rewards.get("infrastructure") == 1.0)


def trial_scenario_outcome(job_dir: Path, trial: TrialResult) -> tuple[Literal["passed", "failed"], list[str]]:
    """Classify deterministic task failure without conflating it with evidence validity."""
    path = job_dir / trial.trial_name / "verifier/mechanical.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    failures = raw.get("failures")
    if not isinstance(failures, list) or any(not isinstance(value, str) or not value for value in failures):
        raise ValueError("mechanical verifier evidence has invalid failures")
    success = trial_mechanical_success(trial)
    if success == bool(failures):
        raise ValueError("mechanical verifier reward and failure evidence disagree")
    return ("passed", []) if success else ("failed", failures)


def _final_response(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    steps = document.get("steps") if isinstance(document, dict) else None
    if not isinstance(steps, list):
        raise ValueError("trajectory is not a valid ATIF document")
    messages = [
        step["message"]
        for step in steps
        if isinstance(step, dict) and step.get("source") == "agent" and isinstance(step.get("message"), str) and step["message"].strip()
    ]
    if not messages:
        raise ValueError("trajectory has no final assistant response")
    return messages[-1]


_CMD_STRING = re.compile(r'cmd:"((?:\\.|[^"\\])*)"')


def _sanitized_iwe_commands(path: Path) -> list[list[str]]:
    """Extract only bounded IWE argv; never expose arbitrary shell or tool payloads."""
    document = json.loads(path.read_text(encoding="utf-8"))
    steps = document.get("steps") if isinstance(document, dict) else None
    if not isinstance(steps, list):
        raise ValueError("trajectory is not a valid ATIF document")
    commands: list[list[str]] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("source") != "agent":
            continue
        tool_calls = step.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            arguments = call.get("arguments") if isinstance(call, dict) else None
            source = arguments.get("input") if isinstance(arguments, dict) else None
            if not isinstance(source, str):
                continue
            match = _CMD_STRING.search(source)
            if match is None:
                continue
            try:
                command = json.loads(f'"{match.group(1)}"')
                argv = shlex.split(command)
            except (json.JSONDecodeError, ValueError):
                continue
            if not argv or argv[0] != "iwe":
                continue
            if len(argv) > 64 or any(
                len(value) > 512 or any(ord(char) < 32 and char not in "\t\n\r" for char in value)
                for value in argv
            ):
                raise ValueError("IWE command evidence exceeds the safe bounded format")
            commands.append(argv)
            if len(commands) > 64:
                raise ValueError("too many IWE commands in trajectory evidence")
    return commands


def trial_evidence(
    job_dir: Path,
    trial_name: str,
    *,
    include_command_evidence: bool = True,
) -> list[tuple[EvidenceKind, str]]:
    root = job_dir / trial_name
    trajectory = root / "agent/trajectory.json"
    result_path = root / "result.json"
    infrastructure_reward = 1.0
    if result_path.is_file():
        trial = TrialResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        infrastructure_reward = trial.verifier_result.rewards.get("infrastructure", 0.0)
    if not trajectory.is_file():
        raise ValueError(f"trial {trial_name} has no trajectory evidence")
    evidence: list[tuple[EvidenceKind, str]] = [
        (
            "infrastructure",
            f"Harbor separate verifier returned infrastructure={infrastructure_reward:g}",
        ),
        ("response", f"trajectory sha256={sha256_file(trajectory)}\nfinal assistant response:\n{_final_response(trajectory)}"),
    ]
    if include_command_evidence:
        evidence.append((
            "command",
            "sanitized IWE argv only; arbitrary shell commands and outputs are excluded\n"
            + json.dumps(
                {"protocol": "iwe-command-evidence-v1", "commands": _sanitized_iwe_commands(trajectory)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ))
    paths = {
        "oracle": root / "verifier/oracle.json",
        "workspace": root / "verifier/workspace-manifest.json",
        "mechanical": root / "verifier/mechanical.json",
        "postconditions": root / "verifier/postconditions.json",
        "fallback_attestation": root / "verifier/fallback-attestation.json",
        "stdout": root / "verifier/test-stdout.txt",
        "stderr": root / "verifier/test-stderr.txt",
    }
    for name, path in paths.items():
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if name == "mechanical":
                mechanical = json.loads(text)
                if mechanical.get("measurement_confounded") is True:
                    evidence.append((
                        "measurement",
                        json.dumps(
                            {
                                "measurement_reason": "compound_setup_task",
                                "measurement_status": "conservative_total",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ))
            evidence.append((EVIDENCE_KINDS[name], f"{name} sha256={sha256_file(path)}\n{text[:8000]}"))
    return evidence


def normalized_judge_input(messages: list[dict[str, str]]) -> bytes | None:
    """Return the canonical equivalence key for a current judge evidence envelope."""
    if len(messages) != 2:
        raise ValueError("valid cell has malformed judge messages")
    try:
        envelope = json.loads(messages[1]["content"])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(envelope, dict) or envelope.get("protocol") != "iwe-harbor-judge-v1":
        return None
    current_mechanical_protocol = False
    for item in envelope.get("evidence", []):
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if item.get("kind") == "response" and text.startswith("trajectory sha256=") and "\n" in text:
            item["text"] = text.split("\n", 1)[1]
        elif re.match(r"^(oracle|workspace|mechanical) sha256=[0-9a-f]+\n", text):
            item["text"] = text.split("\n", 1)[1]
            if text.startswith("mechanical sha256="):
                payload = json.loads(item["text"])
                current_mechanical_protocol = "measurement_confounded" in payload
                payload.pop("trajectory_sha256", None)
                item["text"] = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if not current_mechanical_protocol:
        return None
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _normalized_judge_input(cell: dict) -> bytes | None:
    messages = cell.get("judge_messages")
    if not isinstance(messages, list):
        raise ValueError("valid cell has malformed judge messages")
    return normalized_judge_input(messages)


def validate_equivalent_judgements(cells: list[dict]) -> None:
    """Invalidate every member of an inconsistent equivalent-input cohort."""
    groups: dict[tuple[str, str, bytes], list[dict]] = {}
    for cell in cells:
        if not cell.get("valid"):
            continue
        fingerprint = _normalized_judge_input(cell)
        if fingerprint is not None:
            groups.setdefault((cell["arm"], cell["scenario_id"], fingerprint), []).append(cell)
    for (_, _, fingerprint), members in groups.items():
        vectors = {json.dumps(cell["scores"], sort_keys=True, separators=(",", ":")) for cell in members}
        if len(vectors) <= 1:
            continue
        for cell in members:
            cell["valid"] = False
            cell["pass"] = False
            cell["required_pass"] = False
            cell["invalid_reason"] = "equivalent_evidence_judge_inconsistency"
            cell["scores"] = {}



def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if any(not math.isfinite(value) for value in values):
        raise ValueError("statistics require finite observations")
    if not values:
        return {"n": 0, "mean": None, "sd": None, "p05": None, "p25": None, "p50": None, "p75": None, "p95": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else None,
        "p05": _percentile(values, 0.05),
        "p25": _percentile(values, 0.25),
        "p50": _percentile(values, 0.50),
        "p75": _percentile(values, 0.75),
        "p95": _percentile(values, 0.95),
    }


def _group_statistics(cells: list[dict], *, cohort: str = "available-valid") -> dict[str, object]:
    valid = [cell for cell in cells if cell["valid"]]
    dimension_sets = {frozenset(cell["scores"]) for cell in valid}
    if len(dimension_sets) > 1:
        raise ValueError("valid cells in one arm cohort have inconsistent score dimensions")
    dimensions = tuple(name for name in DIMENSIONS if name in next(iter(dimension_sets), frozenset()))
    return {
        "cohort": cohort,
        "scores": {name: distribution([cell["scores"][name] for cell in valid]) for name in dimensions},
        "wall_time_seconds": distribution([cell["wall_time_seconds"] for cell in valid]),
        "n_input_tokens": distribution([float(cell["n_input_tokens"]) for cell in valid]),
        "n_cache_tokens": distribution([float(cell["n_cache_tokens"]) for cell in valid]),
        "n_output_tokens": distribution([float(cell["n_output_tokens"]) for cell in valid]),
        "cost_usd": distribution([cell["cost_usd"] for cell in valid]),
    }


def _arm_groups(cells: list[dict], arms: list[str]) -> dict[str, object]:
    return {arm: _group_statistics([cell for cell in cells if cell["arm"] == arm]) for arm in arms}


def _paired_statistics(
    control: dict[tuple[str, int], dict],
    treatment: dict[tuple[str, int], dict],
    keys: list[tuple[str, int]],
) -> dict[str, object]:
    common = [key for key in keys if control[key]["valid"] and treatment[key]["valid"]]
    dimensions = sorted(
        set.intersection(*(set(control[key]["scores"]) & set(treatment[key]["scores"]) for key in common))
        if common else set()
    )
    result: dict[str, object] = {
        "cohort": "common-valid",
        "n": len(common),
        "pair_ids": [{"scenario_id": scenario, "sample": sample} for scenario, sample in common],
        "arm_distributions": {
            "control": _group_statistics([control[key] for key in common], cohort="common-valid"),
            "treatment": _group_statistics([treatment[key] for key in common], cohort="common-valid"),
        },
        "score_delta_treatment_minus_control": {
            name: distribution([treatment[key]["scores"][name] - control[key]["scores"][name] for key in common])
            for name in dimensions
        },
    }
    result["metric_delta_treatment_minus_control"] = {
        field: distribution([float(treatment[key][field] - control[key][field]) for key in common])
        for field in METRICS
    }
    return result


@dataclass(frozen=True)
class SummaryCohort:
    cells: list[dict]
    expected_identities: set[tuple[str, str, int]]
    arms: list[str]
    scenarios: list[str]
    families: list[str]
    analysis: AnalysisPlan


@dataclass(frozen=True)
class PairedCohort:
    statistics: dict[str, object]
    common_valid_keys: list[tuple[str, int]]
    excluded_pairs: list[dict[str, object]]


def _validate_summary_cohort(
    cells: list[dict],
    expected_identities: set[tuple[str, str, int]],
    *,
    expected_families: dict[str, str],
    analysis: AnalysisPlan,
    pipeline_elapsed_seconds: float | None,
) -> SummaryCohort:
    if not expected_identities:
        raise ValueError("expected identity matrix must not be empty")
    if pipeline_elapsed_seconds is not None and (
        not math.isfinite(pipeline_elapsed_seconds) or pipeline_elapsed_seconds < 0
    ):
        raise ValueError("pipeline elapsed seconds must be finite and non-negative")
    normalized = sorted(
        (CellRecord.model_validate(cell).model_dump(mode="json", by_alias=True) for cell in cells),
        key=lambda cell: (cell["scenario_id"], cell["sample"], cell["arm"]),
    )
    identities = {(cell["arm"], cell["scenario_id"], cell["sample"]) for cell in normalized}
    if len(normalized) != len(identities):
        raise ValueError("cell identity matrix contains duplicates")
    if identities != expected_identities:
        missing = sorted(expected_identities - identities)
        unexpected = sorted(identities - expected_identities)
        raise ValueError(f"cell identity matrix mismatch: missing={missing}, unexpected={unexpected}")
    for cell in normalized:
        if cell["family"] != expected_families.get(cell["scenario_id"]):
            raise ValueError("cell family does not match the sealed scenario catalog")
    arms = sorted({identity[0] for identity in expected_identities})
    if set(arms) != set(analysis.arms):
        raise ValueError("analysis arms do not match the identity matrix")
    return SummaryCohort(
        normalized, expected_identities, arms,
        sorted({identity[1] for identity in expected_identities}),
        sorted({cell["family"] for cell in normalized}), analysis,
    )


def _paired_cohort(cohort: SummaryCohort) -> PairedCohort:
    if cohort.analysis.kind != "paired":
        return PairedCohort({}, [], [])
    control_arm = cohort.analysis.control_arm
    treatment_arm = cohort.analysis.treatment_arm
    control = {(cell["scenario_id"], cell["sample"]): cell for cell in cohort.cells if cell["arm"] == control_arm}
    treatment = {(cell["scenario_id"], cell["sample"]): cell for cell in cohort.cells if cell["arm"] == treatment_arm}
    planned_keys = sorted({(scenario, sample) for _, scenario, sample in cohort.expected_identities})
    common = [key for key in planned_keys if control[key]["valid"] and treatment[key]["valid"]]
    excluded = []
    for scenario_id, sample in planned_keys:
        reasons = [
            f"{arm}:{rows[(scenario_id, sample)]['invalid_reason']}"
            for arm, rows in ((control_arm, control), (treatment_arm, treatment))
            if not rows[(scenario_id, sample)]["valid"]
        ]
        if reasons:
            excluded.append({"scenario_id": scenario_id, "sample": sample, "reasons": reasons})
    statistics = {
        "control_arm": control_arm,
        "treatment_arm": treatment_arm,
        "overall": _paired_statistics(control, treatment, planned_keys),
        "per_scenario": {
            scenario: _paired_statistics(control, treatment, [key for key in planned_keys if key[0] == scenario])
            for scenario in cohort.scenarios
        },
        "per_family": {
            family: _paired_statistics(
                control, treatment,
                [key for key in planned_keys if control[key]["family"] == family and treatment[key]["family"] == family],
            )
            for family in cohort.families
        },
    }
    return PairedCohort(statistics, common, excluded)


def _grouped_missingness(cells: list[dict], field: str) -> dict[str, dict[str, object]]:
    groups: dict[str, list[dict]] = {}
    for cell in cells:
        groups.setdefault(str(cell[field]), []).append(cell)
    return {
        name: {
            "planned": len(rows),
            "valid": sum(1 for row in rows if row["valid"]),
            "invalid": sum(1 for row in rows if not row["valid"]),
            "invalid_reasons": dict(sorted(Counter(
                row["invalid_reason"] for row in rows if not row["valid"]
            ).items())),
        }
        for name, rows in sorted(groups.items())
    }


def _reliability(cohort: SummaryCohort, paired: PairedCohort) -> dict[str, object]:
    cells, arms = cohort.cells, cohort.arms
    valid_by_arm = {arm: sum(cell["valid"] for cell in cells if cell["arm"] == arm) for arm in arms}
    invalid_by_arm = {arm: sum(not cell["valid"] for cell in cells if cell["arm"] == arm) for arm in arms}
    planned_by_arm = {arm: sum(identity[0] == arm for identity in cohort.expected_identities) for arm in arms}
    paired_run = cohort.analysis.kind == "paired"
    planned_pairs = len(cohort.expected_identities) // 2
    return {
        "planned_cells_by_arm": planned_by_arm,
        "valid_cells_by_arm": valid_by_arm,
        "invalid_cells_by_arm": invalid_by_arm,
        "completion_rate_by_arm": {arm: valid_by_arm[arm] / planned_by_arm[arm] for arm in arms},
        "invalid_reasons_by_arm": {arm: dict(sorted(Counter(
            cell["invalid_reason"] for cell in cells if cell["arm"] == arm and not cell["valid"]
        ).items())) for arm in arms},
        "scenario_failures_by_arm": {arm: sum(
            cell["scenario_outcome"] == "failed" for cell in cells if cell["arm"] == arm
        ) for arm in arms},
        "missingness_by_scenario": _grouped_missingness(cells, "scenario_id"),
        "missingness_by_family": _grouped_missingness(cells, "family"),
        "common_valid_pairs": len(paired.common_valid_keys) if paired_run else None,
        "planned_pairs": planned_pairs if paired_run else None,
        "common_valid_pair_rate": len(paired.common_valid_keys) / planned_pairs if paired_run else None,
        "excluded_pairs": paired.excluded_pairs,
    }


def _available_statistics(cohort: SummaryCohort) -> dict[str, object]:
    return {
        "overall": _arm_groups(cohort.cells, cohort.arms),
        "per_scenario": {key: _arm_groups(
            [cell for cell in cohort.cells if cell["scenario_id"] == key], cohort.arms,
        ) for key in cohort.scenarios},
        "per_family": {key: _arm_groups(
            [cell for cell in cohort.cells if cell["family"] == key], cohort.arms,
        ) for key in cohort.families},
    }


def _timing_summary(
    cohort: SummaryCohort, paired: PairedCohort, pipeline_elapsed_seconds: float | None,
) -> dict[str, float | None]:
    available = sum(cell["wall_time_seconds"] or 0.0 for cell in cohort.cells if cell["valid"])
    common: float | None = None
    if cohort.analysis.kind == "paired":
        indexed = {(cell["arm"], cell["scenario_id"], cell["sample"]): cell for cell in cohort.cells}
        common = sum(
            (indexed[(cohort.analysis.control_arm, scenario, sample)]["wall_time_seconds"] or 0.0)
            + (indexed[(cohort.analysis.treatment_arm, scenario, sample)]["wall_time_seconds"] or 0.0)
            for scenario, sample in paired.common_valid_keys
        )
    return {"available_valid_summed_cell_seconds": available,
            "common_valid_summed_cell_seconds": common, "pipeline_elapsed_seconds": pipeline_elapsed_seconds}


def summarize_cells(
    cells: list[dict],
    expected_identities: set[tuple[str, str, int]],
    *,
    expected_families: dict[str, str],
    analysis: AnalysisPlan,
    pipeline_elapsed_seconds: float | None = None,
    run_purpose: str = "diagnostic",
    samples_per_identity: int | None = None,
    preregistered_samples: int | None = None,
) -> "SummaryV6":
    validate_equivalent_judgements(cells)
    cohort = _validate_summary_cohort(
        cells, expected_identities, expected_families=expected_families,
        analysis=analysis, pipeline_elapsed_seconds=pipeline_elapsed_seconds,
    )
    paired_run = analysis.kind == "paired"
    valid = all(cell["valid"] for cell in cohort.cells)
    acceptance = CURRENT_ACCEPTANCE_POLICY.evaluate_groups(cohort.cells, roles=analysis.roles)
    passed = valid and acceptance["pass"]
    paired = _paired_cohort(cohort)
    from .summary import SummaryV6
    return SummaryV6.model_validate({
        "schema_version": 6,
        "analysis": {
            "kind": analysis.kind,
            "absolute": {"arm": analysis.arms[0]} if not paired_run else None,
            "paired": (
                {"control_arm": analysis.control_arm, "treatment_arm": analysis.treatment_arm}
                if paired_run else None
            ),
        },
        "expected_cells": len(expected_identities),
        "observed_cells": len(cohort.cells),
        "valid": valid,
        "pass": passed,
        "evaluation_status": {
            "evidence_integrity": "valid" if valid else "invalid",
            "acceptance": {
                "applicable": True,
                "passed": acceptance["pass"],
                "policy_id": acceptance["policy_id"],
            },
            "comparison": {
                "kind": "descriptive-paired" if paired_run else "absolute",
                "superiority_verdict": "not-asserted" if paired_run else None,
            },
        },
        "acceptance": acceptance,
        "reliability": _reliability(cohort, paired),
        "statistics": {
            "available_valid": _available_statistics(cohort),
            "common_valid_paired": paired.statistics,
        },
        "timing": _timing_summary(cohort, paired, pipeline_elapsed_seconds),
        "measurement_scope": {
            "cell_wall_time": "Harbor worker trial wall clock; excludes judging",
            "tokens_and_cost": "Harbor worker totals; excludes judge usage",
            "pipeline_elapsed": "end-to-end execution including judging",
        },
        "interpretation": {
            "run_purpose": run_purpose,
            "samples_per_identity": samples_per_identity,
            "preregistered_samples": preregistered_samples,
            "inferential_status": (
                "diagnostic-only"
                if run_purpose != "production"
                or samples_per_identity is None
                or preregistered_samples is None
                or samples_per_identity < preregistered_samples
                else "production-descriptive"
            ),
        },
        "cells": cohort.cells,
    })


def write_summary(
    path: Path,
    cells: list[dict],
    expected_identities: set[tuple[str, str, int]],
    *,
    expected_families: dict[str, str],
    analysis: AnalysisPlan,
    pipeline_elapsed_seconds: float | None = None,
    run_purpose: str = "diagnostic",
    samples_per_identity: int | None = None,
    preregistered_samples: int | None = None,
) -> "SummaryV6":
    summary = summarize_cells(
        cells,
        expected_identities,
        expected_families=expected_families,
        analysis=analysis,
        pipeline_elapsed_seconds=pipeline_elapsed_seconds,
        run_purpose=run_purpose,
        samples_per_identity=samples_per_identity,
        preregistered_samples=preregistered_samples,
    )
    atomic_write_json(path, summary.model_dump(mode="json", by_alias=True))
    return summary
