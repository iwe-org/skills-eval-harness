from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from collections.abc import Callable

import pytest


from skills_eval_harness.bundle import (
    BundleLayout,
    CurrentRunManifest,
    ManifestExecution,
    SelectedSkillMetadata,
    ValidatedBundle,
    validate_run_bundle,
)
from skills_eval_harness.hashing import (
    sha256_file,
)
from skills_eval_harness.models import Agent, AnalysisPlan, HarnessConfig, Judge, Suite
from skills_eval_harness.publish import publish
from skills_eval_harness.provenance import Provenance, seal_run, verify_run_seal
from skills_eval_harness.telemetry import validate_device_telemetry
from skills_eval_harness.summary import SummaryV6
from support.bundle_builder import BundleBuilder


SHA = "a" * 64
COMMIT = "b" * 40


@pytest.fixture
def mocked_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(run_dir: Path, *, require_seal: bool) -> ValidatedBundle:
        if require_seal:
            verify_run_seal(run_dir)
        raw_manifest = json.loads((run_dir / "run-manifest.json").read_text())
        suite = Suite.model_validate(raw_manifest["suite"])
        manifest = CurrentRunManifest.model_construct(
            schema_version=1,
            run_id=raw_manifest["run_id"],
            suite=suite,
            suite_repository_path="evals/suites/demo.yaml",
            agent=raw_manifest["agent"],
            agent_version=raw_manifest["agent_version"],
            node_version=raw_manifest["node_version"],
            worker_auth_mode="api-key",
            judge_auth_mode="api-key",
            evidence_protocol="judge-evidence-v3",
            samples=raw_manifest["samples"],
            suite_default_samples=raw_manifest["suite_default_samples"],
            run_purpose=raw_manifest["run_purpose"],
            datasets={"arm": "datasets/arm"},
            execution=ManifestExecution(
                global_concurrency=1,
                judge_concurrency=4,
                arm_concurrency_batches=[{"arm": 1}],
            ),
        )
        config = HarnessConfig.model_construct(
            agents={
                "codex": Agent.model_construct(
                    model="openai/test", version="0.147.0", reasoning="medium"
                )
            },
            judge=Judge.model_construct(model="judge-test", reasoning="low"),
        )
        return ValidatedBundle(
            layout=BundleLayout.at(run_dir),
            manifest=manifest,
            provenance=Provenance.model_validate_json(
                (run_dir / "provenance.json").read_text()
            ).validated(),
            config=config,
            suite=suite,
            analysis=AnalysisPlan.from_suite(
                suite, families={"scenario": "read"}, samples=raw_manifest["samples"]
            ),
            catalog={},
            cells=(),
            summary=SummaryV6.model_validate_json(
                (run_dir / "summary.json").read_text()
            ),
            telemetry=validate_device_telemetry(run_dir / "device-telemetry.json"),
            skill=SelectedSkillMetadata(name="demo", version="1.0.0"),
        )

    monkeypatch.setattr("skills_eval_harness.publish.validate_run_bundle", validate)


def git(root: Path, *args: str) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    }
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=environment
    )


def commit_repository(root: Path, files: dict[str, str], remote: str) -> str:
    root.mkdir()
    git(root, "init", "-q")
    git(root, "remote", "add", "origin", remote)
    for relative, payload in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def provenance(dirty: bool = False) -> Provenance:
    return Provenance(
        source_url="https://github.com/acme/skills/tree/" + COMMIT + "/skills/demo",
        source_commit=COMMIT,
        source_tree_sha256=SHA,
        selected_skill="demo",
        selected_skill_sha256=SHA,
        selected_skill_harbor_sha256=SHA,
        runtime_version="1.2.3",
        runtime_sha256=SHA,
        harness_commit=COMMIT,
        harness_tree_sha256=SHA,
        harness_dirty=dirty,
        suite_sha256=SHA,
        effective_suite_sha256=SHA,
        scenario_catalog_sha256=SHA,
        config_sha256=SHA,
        fixture_registry_sha256=SHA,
        harbor_version="0.21.0",
        node_version="22.23.2",
        agent_versions={"codex": "0.147.0", "claude": "2.1.233"},
        task_checksums={"task": SHA},
        image_digests={"agent": SHA, "verifier": SHA},
        fixture_sources={
            "fixture": {
                "repository": "https://github.com/acme/fixture",
                "commit": COMMIT,
                "tree": COMMIT,
                "payload_sha256": SHA,
            }
        },
        worker_auth_mode="api-key",
        judge_auth_mode="api-key",
        judge_concurrency=4,
    )


def setup(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    run = root / "run"
    run.mkdir(parents=True)
    git(root, "init")
    git(
        root,
        "remote",
        "add",
        "origin",
        "https://github.com/bulbigood/skills-eval-harness.git",
    )
    summary = {
        "schema_version": 6,
        "valid": True,
        "pass": True,
        "expected_cells": 1,
        "observed_cells": 1,
        "analysis": {"kind": "absolute", "absolute": {"arm": "arm"}, "paired": None},
        "evaluation_status": {
            "evidence_integrity": "valid",
            "acceptance": {
                "applicable": True,
                "passed": True,
                "policy_id": "dimension-sample-rate-v2",
            },
            "comparison": {"kind": "absolute", "superiority_verdict": None},
        },
        "acceptance": {
            "policy_id": "dimension-sample-rate-v2",
            "pass": True,
            "score_thresholds": {"safety": 5},
            "sample_pass_rate_thresholds": {"safety": 1.0},
            "criteria": [],
        },
        "reliability": {
            "planned_cells_by_arm": {"arm": 1},
            "valid_cells_by_arm": {"arm": 1},
            "invalid_cells_by_arm": {"arm": 0},
            "completion_rate_by_arm": {"arm": 1.0},
            "invalid_reasons_by_arm": {"arm": {}},
            "scenario_failures_by_arm": {"arm": 0},
            "missingness_by_scenario": {},
            "missingness_by_family": {},
            "excluded_pairs": [],
            "common_valid_pairs": None,
            "planned_pairs": None,
            "common_valid_pair_rate": None,
        },
        "statistics": {
            "available_valid": {
                "overall": {"arm": {"scores": {}}},
                "per_scenario": {},
                "per_family": {},
            },
            "common_valid_paired": {},
        },
        "timing": {
            "available_valid_summed_cell_seconds": 1.0,
            "common_valid_summed_cell_seconds": None,
            "pipeline_elapsed_seconds": 2.0,
        },
        "measurement_scope": {
            "cell_wall_time": "test",
            "tokens_and_cost": "test",
            "pipeline_elapsed": "test",
        },
        "interpretation": {
            "run_purpose": "production",
            "samples_per_identity": 10,
            "preregistered_samples": 10,
            "inferential_status": "production-descriptive",
        },
        "cells": [],
    }
    (run / "summary.json").write_text(json.dumps(summary))
    (run / "provenance.json").write_text(provenance().model_dump_json())
    suite = {
        "schema_version": 1,
        "id": "demo-suite",
        "kind": "absolute",
        "default_samples": 10,
        "scenarios": ["scenario"],
        "arms": [{"id": "arm", "skill": True, "role": None}],
    }
    (run / "run-manifest.json").write_text(
        json.dumps(
            {
                "run_id": "canonical-production-run",
                "run_purpose": "production",
                "agent": "codex",
                "agent_version": "0.147.0",
                "node_version": "22.23.2",
                "samples": 10,
                "suite_default_samples": 10,
                "suite": suite,
            }
        )
    )
    (run / "jobs/job/trial/agent").mkdir(parents=True)
    (run / "jobs/job/trial/verifier").mkdir(parents=True)
    (run / "jobs/job/lock.json").write_text("{}")
    (run / "jobs/job/result.json").write_text("{}")
    (run / "jobs/job/trial/agent/trajectory.json").write_text("{}")
    (run / "jobs/job/trial/verifier/oracle.json").write_text("{}")
    (run / "jobs/job/trial/verifier/mechanical.json").write_text("{}")
    (run / "jobs/job/trial/verifier/workspace-manifest.json").write_text("{}")
    (run / "jobs/job/trial/verifier/test-stdout.txt").write_text("ok")
    (run / "jobs/job/trial/verifier/test-stderr.txt").write_text("")
    (run / "inputs").mkdir()
    for name in (
        "config.yaml",
        "scenario-catalog.yaml",
        "suite.yaml",
        "effective-suite.json",
        "fixture-sources.json",
    ):
        (run / "inputs" / name).write_text("{}")
    (run / "inputs/config.yaml").write_text(
        "agents:\n  codex:\n    model: openai/test\n    reasoning: medium\njudge:\n  model: judge-test\n  reasoning: low\n"
    )
    (run / "inputs/selected-skill").mkdir()
    (run / "inputs/selected-skill/SKILL.md").write_text(
        "---\nname: demo\nmetadata:\n  version: '1.0.0'\n---\nbody\n"
    )
    for name in ("runtime", "source-commit-object", "harness-commit-object"):
        (run / "inputs" / name).write_bytes(b"fixture")
    (run / "inputs/fixture-commit-objects").mkdir()
    (run / "inputs/fixture-commit-objects/fixture").write_bytes(b"fixture commit")
    (run / "datasets/arm/task/tests").mkdir(parents=True)
    (run / "datasets/arm/task/task.toml").write_text("version = '1.0'")
    (run / "datasets/arm/task/instruction.md").write_text("task")
    (run / "datasets/arm/task/tests/verify.py").write_text("print('ok')")
    (run / "cells").mkdir()
    (run / "cells/arm--scenario--1.json").write_text(
        json.dumps(
            {
                "evidence": [{"id": "E0001", "kind": "oracle", "text": "fact"}],
                "judge_messages": [
                    {"role": "system", "content": "judge"},
                    {"role": "user", "content": "evidence"},
                ],
                "verdict": {"dimensions": []},
            }
        )
    )
    (run / "device-telemetry.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "started_unix_ms": 1000,
                "finished_unix_ms": 2000,
                "host": {
                    "logical_cpus": 2,
                    "total_memory_bytes": 4096,
                    "total_swap_bytes": 0,
                    "docker_metrics_available": True,
                    "telemetry_scope": "whole-host",
                    "network_scope": "default-route-interfaces",
                    "disk_scope": "physical-block-devices",
                    "filesystem_scope": "root-filesystem",
                },
                "samples": [
                    {
                        "elapsed_ms": 0,
                        "cpu_percent": 25.0,
                        "load1": 0.5,
                        "mem_available_bytes": 2048,
                        "swap_free_bytes": 0,
                        "running_containers": 2,
                        "network_rx_bytes": 100,
                        "network_tx_bytes": 200,
                        "disk_read_bytes": 300,
                        "disk_write_bytes": 400,
                        "network_rx_bytes_per_second": 0.0,
                        "network_tx_bytes_per_second": 0.0,
                        "disk_read_bytes_per_second": 0.0,
                        "disk_write_bytes_per_second": 0.0,
                        "rootfs_used_bytes": 1000,
                        "rootfs_free_bytes": 2000,
                    }
                ],
                "peaks": {
                    "cpu_percent": 25.0,
                    "load1": 0.5,
                    "running_containers": 2,
                    "network_rx_bytes_per_second": 0.0,
                    "network_tx_bytes_per_second": 0.0,
                    "disk_read_bytes_per_second": 0.0,
                    "disk_write_bytes_per_second": 0.0,
                    "rootfs_used_bytes": 1000,
                },
                "minima": {
                    "mem_available_bytes": 2048,
                    "swap_free_bytes": 0,
                    "rootfs_free_bytes": 2000,
                },
                "totals": {
                    "network_rx_bytes": 0,
                    "network_tx_bytes": 0,
                    "disk_read_bytes": 0,
                    "disk_write_bytes": 0,
                },
                "docker_oom_events": 0,
                "sampling_errors": 0,
                "terminal_status": "completed",
            }
        )
    )
    seal_run(run)
    return root, run


def build_valid_current_bundle(tmp_path: Path) -> tuple[Path, Path]:
    return BundleBuilder(tmp_path).build()


def test_seal_rejects_omitted_required_file(tmp_path: Path) -> None:
    _, run = setup(tmp_path)
    seal = json.loads((run / "run-seal.json").read_text())
    del seal["files"]["inputs/runtime"]
    (run / "run-seal.json").write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="incomplete|exact publication payload"):
        verify_run_seal(run)


def test_seal_ignores_interpreter_cache_created_after_sealing(tmp_path: Path) -> None:
    _, run = setup(tmp_path)
    cache = run / "inputs/harness-repository/src/package/__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-313.pyc").write_bytes(b"generated cache")

    verify_run_seal(run)


def test_summary_rejects_stale_acceptance_policy(tmp_path: Path) -> None:
    _, run = setup(tmp_path)
    payload = json.loads((run / "summary.json").read_text())
    payload["acceptance"]["policy_id"] = "dimension-sample-rate-v1"

    with pytest.raises(ValueError):
        SummaryV6.model_validate(payload)


def test_publisher_defaults_to_report_without_evidence(
    tmp_path: Path, mocked_validator: None
) -> None:
    root, run = setup(tmp_path)
    renamed = root / "arbitrary-relocated-bundle-name"
    run.rename(renamed)
    output = root / "reports" / "published.md"
    publish(root=root, run_dir=renamed, output=output)
    text = output.read_text()
    assert text.startswith("# Evaluation report\n")
    assert "- Run ID: `canonical-production-run`" in text
    assert "- Publication revision: `unversioned`" in text
    assert "Suite acceptance: **PASS**" in text
    assert "https://github.com/bulbigood/skills-eval-harness" in text
    assert "Sealed evidence: not staged with this report" in text
    assert "<summary>Complete sanitized device telemetry</summary>" in text
    assert '\n  "cpu_percent_max":' in text
    assert '"p50"' not in text
    assert "median" not in text.lower()
    assert "### Per family" not in text
    assert "Complete sanitized summary JSON" not in text
    assert "Complete task identity map" not in text
    assert "Runtime: `IWE " in text
    assert output.with_suffix(".md.sha256").is_file()
    assert not output.with_suffix(".evidence").exists()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert set(staged) == {"reports/published.md", "reports/published.md.sha256"}


def test_publisher_can_include_revalidated_evidence(
    tmp_path: Path, mocked_validator: None
) -> None:
    root, run = setup(tmp_path)
    output = root / "published.md"
    publish(root=root, run_dir=run, output=output, include_evidence=True)
    text = output.read_text()
    assert "Sealed evidence" in text
    evidence = root / "published.evidence"
    assert (evidence / "summary.json").is_file()
    assert (evidence / "cells/arm--scenario--1.json").is_file()
    assert (evidence / "jobs/job/lock.json").is_file()
    assert (evidence / "device-telemetry.json").is_file()
    seal = json.loads((run / "run-seal.json").read_text())
    assert all(
        (evidence / relative).is_file() and sha256_file(evidence / relative) == digest
        for relative, digest in seal["files"].items()
    )
    assert (evidence / "run-seal.json").is_file()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    assert set(staged) >= {
        "published.md",
        "published.md.sha256",
        "published.evidence/summary.json",
        "published.evidence/device-telemetry.json",
    }


def test_publisher_rejects_failed_incomplete_dirty_or_overwrite(
    tmp_path: Path, mocked_validator: None
) -> None:
    root, run = setup(tmp_path)
    output = root / "published.md"
    summary = json.loads((run / "summary.json").read_text())
    summary["pass"] = False
    summary["acceptance"]["pass"] = False
    summary["evaluation_status"]["acceptance"]["passed"] = False
    (run / "summary.json").write_text(json.dumps(summary))
    seal_run(run)
    publish(root=root, run_dir=run, output=output)
    assert "Suite acceptance: **FAIL**" in output.read_text()
    output.unlink()
    output.with_suffix(".md.sha256").unlink()
    subprocess.run(["git", "reset", "-q"], cwd=root, check=True)
    (run / "summary.json").write_text(
        json.dumps({**summary, "pass": True, "observed_cells": 0})
    )
    seal_run(run)
    with pytest.raises(ValueError, match="incomplete"):
        publish(root=root, run_dir=run, output=output)
    (run / "summary.json").write_text(json.dumps({**summary, "pass": True}))
    (run / "provenance.json").write_text(provenance(True).model_dump_json())
    seal_run(run)
    with pytest.raises(ValueError, match="clean"):
        publish(root=root, run_dir=run, output=output)


def test_publisher_rejects_tampered_sealed_artifact(
    tmp_path: Path, mocked_validator: None
) -> None:
    root, run = setup(tmp_path)
    summary = json.loads((run / "summary.json").read_text())
    summary["pass"] = False
    (run / "summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="sealed artifact mismatch"):
        publish(root=root, run_dir=run, output=root / "published.md")


def test_device_telemetry_rejects_sensitive_or_unexpected_fields(
    tmp_path: Path,
) -> None:
    _, run = setup(tmp_path)
    telemetry = run / "device-telemetry.json"
    payload = json.loads(telemetry.read_text())
    validate_device_telemetry(telemetry)
    payload["host"]["hostname"] = "private-runner-01"
    telemetry.write_text(json.dumps(payload))
    seal_run(run)
    with pytest.raises(ValueError, match="device telemetry"):
        validate_device_telemetry(telemetry)


def test_publisher_requires_healthy_current_telemetry_and_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocked_validator: None
) -> None:
    root, run = setup(tmp_path)
    output = root / "published.md"
    telemetry = run / "device-telemetry.json"
    payload = json.loads(telemetry.read_text())
    payload["terminal_status"] = "failed"
    telemetry.write_text(json.dumps(payload))
    seal_run(run)
    with pytest.raises(ValueError, match="healthy schema-v2"):
        publish(root=root, run_dir=run, output=output)

    payload["terminal_status"] = "completed"
    telemetry.write_text(json.dumps(payload))
    seal_run(run)
    monkeypatch.setattr(
        "skills_eval_harness.publish.tempfile.mkdtemp",
        lambda **_: (_ for _ in ()).throw(OSError("disk")),
    )
    with pytest.raises(OSError, match="disk"):
        publish(root=root, run_dir=run, output=output)
    assert not (root / ".published.md.publish.lock").exists()


def test_publish_uses_real_bundle_validator_and_rejects_legacy_schema(
    tmp_path: Path,
) -> None:
    root, run = setup(tmp_path)
    summary = json.loads((run / "summary.json").read_text())
    summary["schema_version"] = 4
    (run / "summary.json").write_text(json.dumps(summary))
    seal_run(run)
    with pytest.raises(ValueError, match="only summary schema version 6"):
        publish(root=root, run_dir=run, output=root / "report.md")


def test_publish_validates_sealed_current_bundle_and_writes_markdown_checksum(
    tmp_path: Path,
) -> None:
    root, run = build_valid_current_bundle(tmp_path)
    output = root / "reports/current.md"

    assert validate_run_bundle(run, require_seal=True).summary.schema_version == 6
    publish(root=root, run_dir=run, output=output)

    report = output.read_text()
    assert report.startswith("# Evaluation report\n")
    assert str(tmp_path) not in report
    checksum = output.with_suffix(".md.sha256")
    assert checksum.read_text() == f"{sha256_file(output)}  current.md\n"


def test_publish_validates_fully_unmocked_paired_bundle(tmp_path: Path) -> None:
    root, run = BundleBuilder(tmp_path, kind="paired").build()
    validated = validate_run_bundle(run, require_seal=True)
    assert validated.analysis.kind == "paired"
    assert validated.analysis.roles == {"control": "control", "treatment": "treatment"}
    assert validated.summary.reliability.common_valid_pairs == 1
    assert (
        validated.summary.evaluation_status.comparison.superiority_verdict
        == "not-asserted"
    )
    assert validated.config.agents[validated.manifest.agent].model == "offline-model"
    assert validated.config.agents[validated.manifest.agent].reasoning == "medium"

    output = root / "reports/paired.md"
    publish(root=root, run_dir=run, output=output)
    report = output.read_text()
    assert "Statistical superiority: **not asserted**" in report
    assert "Common-valid paired cohorts and treatment-minus-control deltas" in report
    assert (
        output.with_suffix(".md.sha256").read_text()
        == f"{sha256_file(output)}  paired.md\n"
    )


@pytest.mark.parametrize(
    ("relative", "mutate", "message"),
    [
        (
            "provenance.json",
            lambda value: {**value, "source_commit": "f" * 40},
            "commit object does not match provenance",
        ),
        (
            "cells/ordinary--offline-read--1.json",
            lambda value: {
                **value,
                "evidence": [
                    {**value["evidence"][0], "text": "resealed forgery"},
                    *value["evidence"][1:],
                ],
            },
            "evidence does not reproduce",
        ),
        (
            "cells/ordinary--offline-read--1.json",
            lambda value: {**value, "pass": False},
            "pass flags do not derive",
        ),
    ],
)
def test_resealed_semantic_tampering_reaches_bundle_validators(
    tmp_path: Path,
    relative: str,
    mutate: Callable[[dict], dict],
    message: str,
) -> None:
    _, run = build_valid_current_bundle(tmp_path)
    path = run / relative
    payload = json.loads(path.read_text())
    path.write_text(json.dumps(mutate(payload)))
    seal_run(run)
    with pytest.raises(ValueError, match=message):
        validate_run_bundle(run, require_seal=True)


@pytest.mark.parametrize(
    ("kind", "mutation", "message"),
    [
        ("absolute", "config-model", "canonical registries"),
        ("absolute", "config-reasoning", "canonical registries"),
        ("absolute", "provenance-source-commit", "commit object"),
        ("absolute", "provenance-skill-digest", "skill snapshot"),
        ("paired", "suite-role", "paired suites require"),
        ("absolute", "summary-analysis", "summary does not recompute"),
        ("absolute", "cell-evidence", "evidence does not reproduce"),
        ("absolute", "cell-verdict", "scores or pass flags"),
    ],
)
def test_named_builder_mutations_are_resealed_and_rejected_semantically(
    tmp_path: Path,
    kind: str,
    mutation: str,
    message: str,
) -> None:
    _, run = BundleBuilder(tmp_path, kind=kind, mutations=(mutation,)).build()
    verify_run_seal(run)
    with pytest.raises(ValueError, match=message):
        validate_run_bundle(run, require_seal=True)


@pytest.mark.parametrize(
    "checkpoint",
    ["evidence-installed", "checksum-installed", "report-installed", "staged"],
)
def test_publication_transaction_rolls_back_every_install_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocked_validator: None,
    checkpoint: str,
) -> None:
    root, run = setup(tmp_path)
    output = root / "published.md"
    raw_index = subprocess.run(
        ["git", "rev-parse", "--git-path", "index"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    index = Path(raw_index) if Path(raw_index).is_absolute() else root / raw_index
    before = index.read_bytes() if index.exists() else None

    def fail(name: str) -> None:
        if name == checkpoint:
            raise OSError(f"fault after {name}")

    monkeypatch.setattr("skills_eval_harness.publish._publication_checkpoint", fail)
    with pytest.raises(OSError, match="fault after"):
        publish(root=root, run_dir=run, output=output, include_evidence=True)
    assert (index.read_bytes() if index.exists() else None) == before
    assert not output.exists() and not output.with_suffix(".md.sha256").exists()
    assert not output.with_suffix(".evidence").exists()
    assert not list(root.glob(".publication-*"))
    assert not list(root.glob(".*.publish.lock"))

    monkeypatch.setattr(
        "skills_eval_harness.publish._publication_checkpoint", lambda _: None
    )
    assert (
        publish(root=root, run_dir=run, output=output, include_evidence=True) == output
    )
