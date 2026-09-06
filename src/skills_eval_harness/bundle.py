"""Shared fail-closed validation for completed run bundles."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

import yaml
from pydantic import Field

from .dataset import _runtime_relationships, scenario_map
from .fixtures import materialized_fixture_path
from .hashing import (
    canonical_json,
    git_object_sha1,
    git_tree_sha1,
    harbor_content_sha256,
    harbor_skill_sha256,
    sha256_bytes,
    sha256_file,
    sha256_tree,
)
from .judge import JUDGE_SCALE, Evidence, build_evidence, build_judge_messages, derive_cell_outcome, judge_messages_match, validate_verdict
from .models import AnalysisPlan, HarnessConfig, StrictModel, Suite, load_config, load_suite, scenario_family, validate_run_id
from .provenance import Provenance, verify_harbor_lock, verify_run_seal
from .results import (
    CellRecord,
    summarize_cells,
    trial_evidence,
    trial_scenario_outcome,
    validate_equivalent_judgements,
    validate_job,
)
from .summary import SummaryV6
from .telemetry import DeviceTelemetry, validate_device_telemetry


@dataclass(frozen=True)
class BundleLayout:
    root: Path
    summary: Path
    manifest: Path
    provenance: Path
    telemetry: Path
    seal: Path
    config: Path
    suite: Path
    catalog: Path
    effective_suite: Path
    fixtures: Path
    skill: Path
    jobs: Path
    cells: Path

    @classmethod
    def at(cls, root: Path) -> "BundleLayout":
        return cls(
            root=root, summary=root / "summary.json", manifest=root / "run-manifest.json",
            provenance=root / "provenance.json", telemetry=root / "device-telemetry.json",
            seal=root / "run-seal.json", config=root / "inputs/config.yaml",
            suite=root / "inputs/suite.yaml", catalog=root / "inputs/scenario-catalog.yaml",
            effective_suite=root / "inputs/effective-suite.json", fixtures=root / "inputs/fixture-sources.json",
            skill=root / "inputs/selected-skill", jobs=root / "jobs", cells=root / "cells",
        )


class ManifestExecution(StrictModel):
    global_concurrency: int = Field(ge=1, le=32)
    judge_concurrency: int = Field(ge=1, le=32)
    arm_concurrency_batches: list[dict[str, int]]


class CurrentRunManifest(StrictModel):
    schema_version: Literal[1]
    run_id: str
    suite: Suite
    suite_repository_path: str
    agent: str
    agent_version: str
    node_version: str
    worker_auth_mode: Literal["api-key", "chatgpt"]
    judge_auth_mode: Literal["api-key", "chatgpt"]
    evidence_protocol: Literal["judge-evidence-v3"]
    samples: int
    suite_default_samples: int
    run_purpose: Literal["diagnostic", "production"]
    execution: ManifestExecution
    datasets: dict[str, str]


class SelectedSkillMetadata(StrictModel):
    name: str
    version: str


@dataclass(frozen=True)
class ValidatedBundle:
    layout: BundleLayout
    manifest: CurrentRunManifest
    provenance: Provenance
    config: HarnessConfig
    suite: Suite
    analysis: AnalysisPlan
    catalog: Mapping[str, Mapping[str, Any]]
    cells: tuple[CellRecord, ...]
    summary: SummaryV6
    telemetry: DeviceTelemetry
    skill: SelectedSkillMetadata


@dataclass(frozen=True)
class BundleInputs:
    layout: BundleLayout
    stored_summary: SummaryV6
    manifest: CurrentRunManifest
    provenance: Provenance
    telemetry: DeviceTelemetry


@dataclass(frozen=True)
class VerifiedInputs:
    bundle: BundleInputs
    config: HarnessConfig
    authored_suite: Suite


@dataclass(frozen=True)
class VerifiedPlan:
    inputs: VerifiedInputs
    suite: Suite
    analysis: AnalysisPlan
    arms: list[dict[str, Any]]
    scenarios: list[str]
    samples: int
    expected_identities: set[tuple[str, str, int]]


@dataclass(frozen=True)
class ReproducedTrials:
    plan: VerifiedPlan
    evidence: dict[tuple[str, str, int], list[dict]]
    scenario_outcomes: dict[tuple[str, str, int], str]
    scenario_failures: dict[tuple[str, str, int], list[str]]
    deterministic_invalid_reasons: dict[tuple[str, str, int], str]


@dataclass(frozen=True)
class ReproducedCells:
    trials: ReproducedTrials
    catalog: dict[str, dict[str, Any]]
    cells: list[dict]



def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def _verify_git_snapshot(
    snapshot: Path,
    commit_object: Path,
    *,
    expected_commit: str,
    expected_sha256: str,
) -> None:
    payload = commit_object.read_bytes()
    if git_object_sha1("commit", payload) != expected_commit:
        raise ValueError("sealed Git commit object does not match provenance")
    first_line = payload.splitlines()[0].decode("ascii", errors="strict")
    if not first_line.startswith("tree ") or git_tree_sha1(snapshot) != first_line.removeprefix("tree "):
        raise ValueError("sealed Git snapshot does not match its commit tree")
    if sha256_tree(snapshot) != expected_sha256:
        raise ValueError("sealed Git snapshot does not match its SHA-256 identity")


def _verify_git_commit_tree(commit_object: Path, *, expected_commit: str, expected_tree: str) -> None:
    payload = commit_object.read_bytes()
    if git_object_sha1("commit", payload) != expected_commit:
        raise ValueError("sealed Git commit object does not match provenance")
    first_line = payload.splitlines()[0].decode("ascii", errors="strict")
    if first_line != f"tree {expected_tree}":
        raise ValueError("sealed Git commit object does not name the claimed tree")


def _load_bundle_inputs(run_dir: Path, *, require_seal: bool) -> BundleInputs:
    layout = BundleLayout.at(run_dir)
    if require_seal:
        verify_run_seal(run_dir)
    stored_summary_raw = _load_json(layout.summary)
    schema_version = stored_summary_raw.get("schema_version")
    if type(schema_version) is not int or schema_version != 6:
        raise ValueError("only summary schema version 6 is supported")
    telemetry = validate_device_telemetry(layout.telemetry)
    stored_summary = SummaryV6.model_validate(stored_summary_raw)
    manifest = CurrentRunManifest.model_validate(_load_json(layout.manifest))
    validate_run_id(manifest.run_id)
    provenance = Provenance.model_validate_json(
        (run_dir / "provenance.json").read_text(encoding="utf-8")
    ).validated()
    return BundleInputs(layout, stored_summary, manifest, provenance, telemetry)


def _verify_canonical_inputs_and_provenance(bundle: BundleInputs) -> VerifiedInputs:
    layout, provenance = bundle.layout, bundle.provenance
    run_dir = layout.root
    config_path = run_dir / "inputs/config.yaml"
    suite_path = run_dir / "inputs/suite.yaml"
    catalog_path = run_dir / "inputs/scenario-catalog.yaml"
    effective_path = run_dir / "inputs/effective-suite.json"
    fixtures_path = run_dir / "inputs/fixture-sources.json"
    expected_hashes = {
        config_path: provenance.config_sha256,
        suite_path: provenance.suite_sha256,
        catalog_path: provenance.scenario_catalog_sha256,
        effective_path: provenance.effective_suite_sha256,
        fixtures_path: provenance.fixture_registry_sha256,
    }
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in expected_hashes.items()):
        raise ValueError("sealed run inputs do not match provenance")
    config = load_config(config_path)
    expected_images = {
        "agent": config.container.agent_image_id.removeprefix("sha256:"),
        "verifier": config.container.image.rsplit("@sha256:", 1)[1],
    }
    if provenance.image_digests != expected_images:
        raise ValueError("sealed container images do not match provenance")
    if provenance.node_version != config.container.node_version:
        raise ValueError("sealed Node version does not match provenance")
    if provenance.agent_versions != {name: value.version for name, value in config.agents.items()}:
        raise ValueError("sealed agent versions do not match provenance")
    if config.runtimes.get(provenance.runtime_version) != provenance.runtime_sha256:
        raise ValueError("runtime version is not bound to canonical bytes")
    _verify_git_snapshot(
        run_dir / "inputs/source-repository",
        run_dir / "inputs/source-commit-object",
        expected_commit=provenance.source_commit,
        expected_sha256=provenance.source_tree_sha256,
    )
    _verify_git_snapshot(
        run_dir / "inputs/harness-repository",
        run_dir / "inputs/harness-commit-object",
        expected_commit=provenance.harness_commit,
        expected_sha256=provenance.harness_tree_sha256,
    )
    harness_snapshot = run_dir / "inputs/harness-repository"
    canonical_inputs = {
        config_path: harness_snapshot / "evals/config.yaml",
        fixtures_path: harness_snapshot / "evals/fixtures/sources.json",
    }
    if any(
        not canonical.is_file() or sealed.read_bytes() != canonical.read_bytes()
        for sealed, canonical in canonical_inputs.items()
    ):
        raise ValueError("sealed canonical registries do not match the harness commit")
    canonical_catalog = harness_snapshot / "evals/scenarios/iwe.yaml"
    canonical_document = yaml.safe_load(canonical_catalog.read_text(encoding="utf-8"))
    if canonical_document.get("schema_version") != 2:
        raise ValueError("canonical scenario registry must use schema version 2")
    if scenario_map(catalog_path) != scenario_map(canonical_catalog):
        raise ValueError("sealed scenario registry does not match the harness commit")
    source_repository = provenance.source_url.split("/tree/", 1)[0].rstrip("/").removesuffix(".git")
    if (
        f"/tree/{provenance.source_commit}/" not in provenance.source_url
        or source_repository not in {value.rstrip("/").removesuffix(".git") for value in config.skill_repositories}
    ):
        raise ValueError("source URL is not bound to the sealed source commit")
    if sha256_file(run_dir / "inputs/runtime") != provenance.runtime_sha256:
        raise ValueError("sealed runtime snapshot does not match provenance")
    skill_snapshot = run_dir / "inputs/selected-skill"
    if (
        sha256_tree(skill_snapshot) != provenance.selected_skill_sha256
        or harbor_skill_sha256(skill_snapshot) != provenance.selected_skill_harbor_sha256
    ):
        raise ValueError("sealed skill snapshot does not match provenance")
    fixture_registry = _load_json(fixtures_path)
    for name, revision in provenance.fixture_sources.items():
        declared = fixture_registry.get(name)
        declared_repository = declared.get("repository", "").removesuffix(".git") if isinstance(declared, dict) else ""
        if (
            not isinstance(declared, dict)
            or set(declared) != {"repository", "commit"}
            or declared_repository != revision.repository.removesuffix(".git")
            or declared.get("commit") != revision.commit
        ):
            raise ValueError("fixture registry does not match provenance")
        if sha256_tree(run_dir / "inputs/fixtures" / name) != revision.payload_sha256:
            raise ValueError("sealed fixture snapshot does not match provenance")
        if git_tree_sha1(run_dir / "inputs/fixtures" / name) != revision.tree:
            raise ValueError("sealed fixture snapshot does not match the claimed Git tree")
        _verify_git_commit_tree(
            run_dir / "inputs/fixture-commit-objects" / name,
            expected_commit=revision.commit,
            expected_tree=revision.tree,
        )
    authored_suite = load_suite(suite_path)
    return VerifiedInputs(bundle, config, authored_suite)


def _verify_effective_suite_and_plan(inputs: VerifiedInputs) -> VerifiedPlan:
    bundle, authored_suite = inputs.bundle, inputs.authored_suite
    layout, manifest, provenance = bundle.layout, bundle.manifest, bundle.provenance
    run_dir, suite_path, effective_path = layout.root, layout.suite, layout.effective_suite
    effective = _load_json(effective_path)
    if manifest.schema_version != 1 or manifest.suite.model_dump(mode="json") != effective:
        raise ValueError("run manifest does not match the effective suite")
    if manifest.suite_default_samples != authored_suite.default_samples:
        raise ValueError("run manifest default sample count does not match the authored suite")
    if manifest.run_purpose == "production" and (
        effective != authored_suite.model_dump(mode="json")
        or manifest.samples != authored_suite.default_samples
    ):
        raise ValueError("production run does not match the preregistered suite matrix")
    if manifest.run_purpose == "production":
        suite_repository_path = manifest.suite_repository_path
        if (
            not isinstance(suite_repository_path, str)
            or Path(suite_repository_path).parent.as_posix() != "evals/suites"
            or not (run_dir / "inputs/harness-repository" / suite_repository_path).is_file()
            or (run_dir / "inputs/harness-repository" / suite_repository_path).read_bytes() != suite_path.read_bytes()
            or provenance.harness_dirty
        ):
            raise ValueError("production suite is not bound to the sealed canonical harness commit")
    arms = effective.get("arms")
    scenarios = effective.get("scenarios")
    samples = manifest.samples
    if not isinstance(arms, list) or not isinstance(scenarios, list) or not isinstance(samples, int) or samples < 1:
        raise ValueError("invalid run plan identity matrix")
    expected_identities = {
        (arm["id"], scenario_id, sample)
        for arm in arms
        for scenario_id in scenarios
        for sample in range(1, samples + 1)
    }
    effective_suite = Suite.model_validate(effective)
    catalog_payload = yaml.safe_load(layout.catalog.read_text(encoding="utf-8"))
    catalog = {item["id"]: item for item in catalog_payload["scenarios"]}
    expected_families = {
        scenario_id: scenario_family(catalog[scenario_id]) for scenario_id in effective_suite.scenarios
    }
    analysis = AnalysisPlan.from_suite(effective_suite, families=expected_families, samples=samples)
    return VerifiedPlan(inputs, effective_suite, analysis, arms, scenarios, samples, expected_identities)


def _reproduce_harbor_trials(plan: VerifiedPlan) -> ReproducedTrials:
    bundle, config = plan.inputs.bundle, plan.inputs.config
    manifest, provenance, run_dir = bundle.manifest, bundle.provenance, bundle.layout.root
    arms, scenarios, samples = plan.arms, plan.scenarios, plan.samples
    expected_identities = plan.expected_identities
    expected_evidence: dict[tuple[str, str, int], list[dict]] = {}
    expected_scenario_outcomes: dict[tuple[str, str, int], str] = {}
    expected_scenario_failures: dict[tuple[str, str, int], list[str]] = {}
    deterministic_invalid_reasons: dict[tuple[str, str, int], str] = {}
    observed_trials: set[tuple[str, str, int]] = set()
    profile = config.agents[manifest.agent]
    if manifest.agent_version != profile.version:
        raise ValueError("run manifest agent version does not match the sealed config")
    if manifest.node_version != config.container.node_version:
        raise ValueError("run manifest Node version does not match the sealed config")
    if manifest.execution.judge_concurrency != provenance.judge_concurrency:
        raise ValueError("judge concurrency does not match sealed provenance")
    batches = manifest.execution.arm_concurrency_batches
    for arm in arms:
        arm_id = arm["id"]
        dataset = (run_dir / manifest.datasets[arm_id]).resolve()
        if not dataset.is_relative_to(run_dir):
            raise ValueError("dataset path escapes the run directory")
        for task in sorted(path for path in dataset.iterdir() if path.is_dir()):
            key = f"{arm_id}/{task.name}"
            task_manifest_path = task / "manifest.json"
            runtime_unavailable = (
                task_manifest_path.is_file()
                and _load_json(task_manifest_path).get("runtime_mode") == "unavailable"
            )
            virtual_runtime = (
                None
                if runtime_unavailable
                else {"environment/payload/usr/local/bin/iwe": run_dir / "inputs/runtime"}
            )
            if harbor_content_sha256(task, virtual_files=virtual_runtime) != provenance.task_checksums.get(key):
                raise ValueError(f"materialized task mismatch: {key}")
        matching_jobs = []
        for candidate in sorted((run_dir / "jobs").iterdir()):
            if not candidate.is_dir() or not (candidate / "lock.json").is_file():
                continue
            candidate_lock = _load_json(candidate / "lock.json")
            sources = {
                trial.get("task", {}).get("source")
                for trial in candidate_lock.get("trials", [])
                if isinstance(trial, dict) and isinstance(trial.get("task"), dict)
            }
            if sources == {arm_id}:
                matching_jobs.append((candidate, candidate_lock))
        if len(matching_jobs) != 1:
            raise ValueError(f"expected exactly one sealed Harbor job for arm: {arm_id}")
        job_dir, lock = matching_jobs[0]
        job = validate_job(
            job_dir,
            expected_trials=len(scenarios) * samples,
            require_mechanical_success=False,
            allow_failed_trials=True,
        )
        concurrency = max(batch.get(arm_id, 0) for batch in batches)
        verify_harbor_lock(
            provenance,
            lock,
            arm_id=arm_id,
            n_concurrent=concurrency,
            retries=config.execution.retries,
            agent_name=profile.harbor_name,
            agent_version=profile.version,
            reasoning_effort=profile.reasoning,
            model=profile.model,
            skill_enabled=arm["skill"],
        )
        for trial in job.trial_results:
            task_id = trial.task_name.removeprefix("iwe/")
            scenario_id, sample_text = task_id.rsplit("--sample-", 1)
            identity = (arm_id, scenario_id, int(sample_text))
            if identity in observed_trials or identity not in expected_identities:
                raise ValueError("Harbor results do not match the run identity matrix")
            observed_trials.add(identity)
            if trial.exception_info is not None:
                continue
            expected_scenario_outcomes[identity], expected_scenario_failures[identity] = trial_scenario_outcome(
                job_dir, trial
            )
            raw_evidence = trial_evidence(job_dir, trial.trial_name)
            expected_evidence[identity] = [
                item.model_dump(mode="json") for item in build_evidence(raw_evidence)
            ]
    if observed_trials != expected_identities:
        raise ValueError("Harbor results do not cover the run identity matrix")
    return ReproducedTrials(
        plan,
        expected_evidence,
        expected_scenario_outcomes,
        expected_scenario_failures,
        deterministic_invalid_reasons,
    )


def _reproduce_cells(trials: ReproducedTrials) -> ReproducedCells:
    plan = trials.plan
    bundle = plan.inputs.bundle
    manifest, run_dir = bundle.manifest, bundle.layout.root
    arms = plan.arms
    catalog = {
        item["id"]: item
        for item in yaml.safe_load(bundle.layout.catalog.read_text(encoding="utf-8"))["scenarios"]
    }
    cells = []
    equivalence_candidates: list[dict] = []
    stored_equivalence_invalid: set[tuple[str, str, int]] = set()
    relationship_cache: dict[str, dict[str, dict[str, list[str]]]] = {}
    for path in sorted((run_dir / "cells").glob("*.json")):
        raw = _load_json(path)
        cell = CellRecord.model_validate(raw).model_dump(mode="json", by_alias=True)
        expected_name = f"{cell['arm']}--{cell['scenario_id']}--{cell['sample']}.json"
        if path.name != expected_name:
            raise ValueError("cell filename does not match its identity")
        if cell["family"] != scenario_family(catalog[cell["scenario_id"]]):
            raise ValueError("cell family does not match the sealed scenario")
        identity = (cell["arm"], cell["scenario_id"], cell["sample"])
        expected_invalid = trials.deterministic_invalid_reasons.get(identity)
        if expected_invalid is not None and (
            cell["valid"] or cell["invalid_reason"] != expected_invalid
        ):
            raise ValueError(
                "stored deterministic invalid reason does not reproduce from Harbor artifacts"
            )
        if cell["valid"]:
            if cell["evidence"] != trials.evidence[identity]:
                raise ValueError("stored cell evidence does not reproduce from Harbor artifacts")
            if cell["scenario_outcome"] != trials.scenario_outcomes[identity]:
                raise ValueError("stored scenario outcome does not reproduce from Harbor artifacts")
            if cell["scenario_failures"] != trials.scenario_failures[identity]:
                raise ValueError("stored scenario failures do not reproduce from Harbor artifacts")
            evidence = tuple(Evidence.model_validate(item) for item in cell["evidence"])
            oracle_items = [
                item for item in evidence
                if item.kind == "oracle" and item.text.startswith("oracle sha256=")
            ]
            if len(oracle_items) != 1 or "\n" not in oracle_items[0].text:
                raise ValueError("semantic oracle does not match the sealed scenario")
            header, oracle_text = oracle_items[0].text.split("\n", 1)
            oracle = json.loads(oracle_text)
            if header != f"oracle sha256={sha256_bytes(oracle_text.encode())}":
                raise ValueError("semantic oracle evidence digest mismatch")
            scenario = catalog[cell["scenario_id"]]
            if oracle.get("procedure") != scenario["procedure"] or oracle.get("excellent") != scenario["excellent"]:
                raise ValueError("semantic oracle does not match the sealed scenario")
            task_id = f"{cell['scenario_id']}--sample-{cell['sample']:03d}"
            task = run_dir / manifest.datasets[cell["arm"]] / task_id
            scenario_id = cell["scenario_id"]
            if scenario_id not in relationship_cache:
                instruction = (task / "instruction.md").read_text(encoding="utf-8")
                terms = {
                    value.lower()
                    for value in re.findall(r"[A-Za-z0-9_-]{4,}", instruction)
                }
                relationship_cache[scenario_id] = _runtime_relationships(
                    task / "environment/payload/workspace",
                    task / "environment/payload/usr/local/bin/iwe",
                    terms,
                )
            if oracle.get("relationships") != relationship_cache[scenario_id]:
                raise ValueError("semantic oracle relationships do not replay with the sealed runtime")
            before = {
                item["path"]: item["sha256"]
                for item in json.loads((task / "tests/before-tree.json").read_text(encoding="utf-8"))
            }
            excerpts = oracle.get("source_excerpts")
            if not isinstance(excerpts, list) or not excerpts:
                raise ValueError("semantic oracle has no fixture-derived source evidence")
            for excerpt in excerpts:
                if not isinstance(excerpt, dict) or set(excerpt) != {"path", "sha256", "text"}:
                    raise ValueError("invalid semantic oracle source evidence")
                source_path = materialized_fixture_path(run_dir, scenario["fixture"], excerpt["path"])
                if (
                    before.get(excerpt["path"]) != excerpt["sha256"]
                    or not source_path.is_file()
                    or sha256_file(source_path) != excerpt["sha256"]
                    or excerpt["text"] not in source_path.read_text(encoding="utf-8")
                ):
                    raise ValueError("semantic oracle source evidence does not match the fixture baseline")
            verdict = validate_verdict(canonical_json(cell["verdict"]).decode(), evidence)
            arm = next(item for item in arms if item["id"] == cell["arm"])
            scenario_outcome = trials.scenario_outcomes[identity]
            if scenario_outcome not in {"passed", "failed"}:
                raise ValueError("invalid sealed scenario outcome")
            expected_scores, expected_pass, expected_required = derive_cell_outcome(
                verdict,
                role=arm.get("role"),
                agent=manifest.agent,
                scenario_outcome=cast(Literal["passed", "failed"], scenario_outcome),
            )
            if (
                cell["scores"] != expected_scores
                or cell["pass"] is not expected_pass
                or cell["required_pass"] is not expected_required
            ):
                raise ValueError("cell scores or pass flags do not derive from the sealed verdict")
            expected_messages = build_judge_messages(
                scenario=catalog[cell["scenario_id"]], evidence=evidence, scale=JUDGE_SCALE
            )
            if not judge_messages_match(cell["judge_messages"], expected_messages):
                raise ValueError("stored judge messages do not match sealed scenario and evidence")
            equivalence_candidates.append(dict(cell))
        elif cell["invalid_reason"] == "equivalent_evidence_judge_inconsistency":
            if cell["evidence"] != trials.evidence[identity]:
                raise ValueError("inconsistent-judge cell evidence does not reproduce from Harbor artifacts")
            evidence = tuple(Evidence.model_validate(item) for item in cell["evidence"])
            verdict = validate_verdict(canonical_json(cell["verdict"]).decode(), evidence)
            arm = next(item for item in arms if item["id"] == cell["arm"])
            expected_scores, _, _ = derive_cell_outcome(verdict, role=arm.get("role"), agent=manifest.agent)
            expected_messages = build_judge_messages(
                scenario=catalog[cell["scenario_id"]], evidence=evidence, scale=JUDGE_SCALE
            )
            if not judge_messages_match(cell["judge_messages"], expected_messages):
                raise ValueError("inconsistent-judge messages do not match sealed scenario and evidence")
            candidate = dict(cell)
            candidate["valid"] = True
            candidate["scores"] = expected_scores
            equivalence_candidates.append(candidate)
            stored_equivalence_invalid.add(identity)
        cells.append(cell)
    validate_equivalent_judgements(equivalence_candidates)
    reproduced_equivalence_invalid = {
        (cell["arm"], cell["scenario_id"], cell["sample"])
        for cell in equivalence_candidates
        if cell.get("invalid_reason") == "equivalent_evidence_judge_inconsistency"
    }
    if reproduced_equivalence_invalid != stored_equivalence_invalid:
        raise ValueError("equivalent-evidence judge inconsistency does not reproduce from sealed verdicts")
    return ReproducedCells(trials, catalog, cells)


def _recompute_summary(reproduced: ReproducedCells) -> SummaryV6:
    plan = reproduced.trials.plan
    bundle = plan.inputs.bundle
    manifest, stored_summary = bundle.manifest, bundle.stored_summary
    effective_suite, samples = plan.suite, plan.samples
    catalog, cells = reproduced.catalog, reproduced.cells
    expected_families = {
        scenario_id: scenario_family(catalog[scenario_id])
        for scenario_id in effective_suite.scenarios
    }
    recomputed = summarize_cells(
        cells,
        plan.expected_identities,
        expected_families=expected_families,
        analysis=plan.analysis,
        pipeline_elapsed_seconds=stored_summary.timing.pipeline_elapsed_seconds,
        run_purpose=manifest.run_purpose,
        samples_per_identity=samples,
        preregistered_samples=manifest.suite.default_samples,
    )
    if canonical_json(recomputed.model_dump(mode="json", by_alias=True)) != canonical_json(stored_summary.model_dump(mode="json", by_alias=True)):
        raise ValueError("summary does not recompute from sealed cells")
    return recomputed


def _load_selected_skill(layout: BundleLayout) -> SelectedSkillMetadata:
    skill_text = (layout.skill / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\n") or "\n---\n" not in skill_text[4:]:
        raise ValueError("selected skill must have YAML frontmatter")
    metadata = yaml.safe_load(skill_text.split("\n---\n", 1)[0][4:])
    version = metadata.get("metadata", {}).get("version") if isinstance(metadata, dict) else None
    if not isinstance(metadata, dict) or not isinstance(metadata.get("name"), str) or not isinstance(version, str):
        raise ValueError("selected skill frontmatter requires string name and version")
    return SelectedSkillMetadata(name=metadata["name"], version=version)


def validate_run_bundle(run_dir: Path, *, require_seal: bool) -> ValidatedBundle:
    """Validate and independently reproduce a sealed current-schema run bundle."""
    bundle = _load_bundle_inputs(run_dir, require_seal=require_seal)
    verified = _verify_canonical_inputs_and_provenance(bundle)
    plan = _verify_effective_suite_and_plan(verified)
    trials = _reproduce_harbor_trials(plan)
    reproduced = _reproduce_cells(trials)
    summary = _recompute_summary(reproduced)
    return ValidatedBundle(
        layout=bundle.layout,
        manifest=bundle.manifest,
        provenance=bundle.provenance,
        config=verified.config,
        suite=plan.suite,
        analysis=plan.analysis,
        catalog=MappingProxyType({key: MappingProxyType(value) for key, value in reproduced.catalog.items()}),
        cells=tuple(CellRecord.model_validate(cell) for cell in reproduced.cells),
        summary=summary,
        telemetry=bundle.telemetry,
        skill=_load_selected_skill(bundle.layout),
    )
