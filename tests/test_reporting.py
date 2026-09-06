from __future__ import annotations

import os
from pathlib import Path

from skills_eval_harness.models import AnalysisPlan
import pytest

from skills_eval_harness.report_models import (
    ReportContext,
    ReportExecution,
    ReportIdentity,
    ReportProvenance,
    ReportPublication,
    ReportTelemetry,
    validate_publication_filename,
)
from skills_eval_harness.reporting import render_report
from skills_eval_harness.results import summarize_cells

from test_harbor_results import valid_cell
from test_harbor_results import invalid_cell


def context(kind: str = "absolute") -> ReportContext:
    arms = ("skill",) if kind == "absolute" else ("no-skill", "skill")
    roles = (
        {"skill": None}
        if kind == "absolute"
        else {"no-skill": "control", "skill": "treatment"}
    )
    identities = {(arm, "one", sample) for arm in arms for sample in (1, 2)}
    cells = [valid_cell(arm, sample) for arm in arms for sample in (1, 2)]
    summary = summarize_cells(
        cells,
        identities,
        expected_families={"one": "read"},
        analysis=AnalysisPlan(
            kind=kind,
            arms=arms,
            roles=roles,
            scenarios=("one",),
            families={"one": "read"},
            samples=2,
        ),
        pipeline_elapsed_seconds=12.0,
        run_purpose="production",
        samples_per_identity=2,
        preregistered_samples=2,
    )
    sha = "a" * 64
    return ReportContext(
        summary=summary,
        identity=ReportIdentity(
            run_id="run",
            report_revision="v8",
            suite_id="suite",
            suite_kind=kind,
            run_purpose="production",
            arms=tuple(
                {"id": arm, "skill": arm == "skill", "role": roles[arm]} for arm in arms
            ),
        ),
        execution=ReportExecution(
            agent_name="codex",
            agent_version="1.2.3",
            worker_model="model|unsafe",
            worker_reasoning="medium",
            judge_backend="api-key",
            judge_model="judge",
            judge_reasoning="low",
            runtime_version="0.18.0",
            runtime_sha256=sha,
            harbor_version="0.21.0",
            node_version="22.23.2",
            agent_image_sha256=sha,
            verifier_image_sha256=sha,
        ),
        provenance=ReportProvenance(
            skill_name="demo",
            skill_version="1.0.0",
            skill_url="https://example.test/tree/x",
            skill_sha256=sha,
            source_commit="b" * 40,
            source_tree_sha256=sha,
            harness_repository="https://example.test/harness",
            harness_commit="c" * 40,
            harness_tree_sha256=sha,
            config_sha256=sha,
            suite_sha256=sha,
            catalog_sha256=sha,
            effective_suite_sha256=sha,
            fixture_registry_sha256=sha,
            task_checksums={"arm/task": sha},
        ),
        publication=ReportPublication(
            checksum_name="report.md.sha256", evidence_link=None
        ),
        telemetry=ReportTelemetry(
            schema_version=2,
            scope="whole-host",
            network_scope="default-route-interfaces",
            disk_scope="physical-block-devices",
            rootfs_scope="root-filesystem",
            logical_cpus=1,
            total_memory_bytes=1,
            total_swap_bytes=0,
            sample_count=1,
            cpu_percent_max=0.0,
            load1_max=0.0,
            mem_available_bytes_min=1,
            swap_free_bytes_min=0,
            running_containers_max=0,
            docker_oom_events=0,
            terminal_status="completed",
            sampling_errors=0,
            network_rx_bytes_per_second_max=0.0,
            network_tx_bytes_per_second_max=0.0,
            disk_read_bytes_per_second_max=0.0,
            disk_write_bytes_per_second_max=0.0,
            rootfs_used_bytes_max=0,
            rootfs_free_bytes_min=1,
            network_rx_bytes_total=0,
            network_tx_bytes_total=0,
            disk_read_bytes_total=0,
            disk_write_bytes_total=0,
        ),
    )


def test_common_contract_is_shared_by_absolute_and_paired() -> None:
    required = [
        "## Report identity",
        "## Status",
        "## Key results",
        "## Execution and model configuration",
        "## Provenance",
        "## Acceptance policy and result",
        "## Descriptive results",
        "## Failures and reliability",
        "## Timing",
        "## Audit appendix",
    ]
    for kind in ("absolute", "paired"):
        report = render_report(context(kind))
        assert [report.index(section) for section in required] == sorted(
            report.index(section) for section in required
        )
        assert "skill_compliance" in report
        assert "## Key results" in report
        assert "The complete map remains in the sealed bundle." in report
        assert "<summary>Complete task identity map</summary>" not in report
        assert "### Per family" not in report
        assert "Complete sanitized summary JSON" not in report
        assert "canonical map SHA-256" in report
        assert "Deterministic outcome is the verifier's mechanical/postcondition gate" in report
        assert "model\\|unsafe (reasoning: medium)" in report
        assert (
            "- Dimensions: `skill_compliance`, `task_correctness`, `scenario_compliance`"
            in report
        )
        assert report.index("| `skill_compliance` |") < report.index("| `task_correctness` |")
        assert "median" not in report.lower() and '"p50"' not in report


def test_only_paired_report_adds_comparison_semantics() -> None:
    absolute = render_report(context("absolute"))
    paired = render_report(context("paired"))
    assert "Statistical superiority" not in absolute
    assert "treatment-minus-control deltas" not in absolute
    assert "Statistical superiority: **not asserted**" in paired
    assert "treatment-minus-control deltas" in paired
    assert "Excluded pairs" in paired


def test_single_sample_report_states_inference_limit() -> None:
    model = context("paired")
    interpretation = model.summary.interpretation.model_copy(
        update={"samples_per_identity": 1, "preregistered_samples": 1}
    )
    report = render_report(
        model.model_copy(
            update={
                "summary": model.summary.model_copy(
                    update={"interpretation": interpretation}
                )
            }
        )
    )
    assert "this smoke run contains one sample per arm/scenario" in report
    assert "run-to-run variability" in report


def test_report_is_deterministic_and_escapes_untrusted_markdown() -> None:
    model = context("absolute")
    assert render_report(model) == render_report(model)
    assert "model\\|unsafe" in render_report(model)


def test_audit_fence_cannot_be_closed_by_untrusted_backticks() -> None:
    model = context("absolute")
    scope = model.summary.measurement_scope.model_copy(
        update={"cell_wall_time": "```injected"}
    )
    summary = model.summary.model_copy(update={"measurement_scope": scope})
    report = render_report(model.model_copy(update={"summary": summary}))
    audit = report.split("## Audit appendix", 1)[1].split(
        "## Sanitized device telemetry", 1
    )[0]
    assert "Complete machine-readable statistics remain available in the sealed summary JSON." in audit
    assert "```injected" not in audit
    assert "transient raw Harbor operational files" in audit


def test_link_destinations_are_encoded_independently_from_text() -> None:
    original = context("absolute")
    model = original.model_copy(
        update={
            "publication": original.publication.model_copy(
                update={"checksum_name": "x.md.sha256) [INJECT](https://evil.invalid"}
            ),
            "provenance": original.provenance.model_copy(
                update={"skill_url": "https://example.test/a path_(x)"}
            ),
        }
    )
    report = render_report(model)
    assert "](x.md.sha256%29%20%5BINJECT%5D%28https://evil.invalid)" in report
    assert "](https://example.test/a%20path_%28x%29)" in report


@pytest.mark.parametrize(
    "name", ["x) [injected](evil.md", "space name.md", "report.txt", ".md"]
)
def test_publication_filename_rejects_unsafe_link_destinations(name: str) -> None:
    with pytest.raises(ValueError, match="portable Markdown filename"):
        validate_publication_filename(__import__("pathlib").Path(name))


def test_nonempty_failure_ledger_distinguishes_failure_invalid_missing_and_excluded_pair() -> (
    None
):
    model = context("paired")
    cells = [
        valid_cell("no-skill", 1),
        {
            **valid_cell("skill", 1, score=0),
            "pass": False,
            "required_pass": False,
            "scenario_outcome": "failed",
            "scenario_failures": ["deterministic verifier failure"],
        },
        invalid_cell("no-skill", 2, "trial_exception"),
        valid_cell("skill", 2),
    ]
    summary = summarize_cells(
        cells,
        {(arm, "one", sample) for arm in ("no-skill", "skill") for sample in (1, 2)},
        expected_families={"one": "read"},
        analysis=AnalysisPlan(
            kind="paired",
            arms=("no-skill", "skill"),
            roles={"no-skill": "control", "skill": "treatment"},
            scenarios=("one",),
            families={"one": "read"},
            samples=2,
        ),
        pipeline_elapsed_seconds=12.0,
        run_purpose="production",
        samples_per_identity=2,
        preregistered_samples=2,
    )
    report = render_report(model.model_copy(update={"summary": summary}))
    assert "`skill/one/1`: deterministic verifier failure" in report
    assert "`no-skill/one/2`: `trial_exception`" in report
    assert "Scenarios with invalid or missing cells:" in report
    assert "`one`: planned `4`, valid `3`, invalid `1`" in report
    assert "Excluded pairs:" in report and "no-skill" in report and "skill" in report


@pytest.mark.parametrize("kind", ["absolute", "paired"])
def test_canonical_report_matches_complete_golden_bytes(kind: str) -> None:
    golden = Path(__file__).parent / "golden" / f"schema-v6-{kind}.md"
    rendered = render_report(context(kind)).encode()
    if os.environ.get("UPDATE_REPORT_GOLDENS") == "1":
        golden.parent.mkdir(exist_ok=True)
        golden.write_bytes(rendered)
    assert golden.read_bytes() == rendered
