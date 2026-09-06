"""Deterministic, fully offline schema-v6 publication bundle fixtures."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from harbor.models.job.result import JobResult, TrialResult

from skills_eval_harness.dataset import scenario_map
from skills_eval_harness.hashing import (
    atomic_write_json,
    git_tree_sha1,
    harbor_content_sha256,
    harbor_skill_sha256,
    sha256_file,
    sha256_tree,
)
from skills_eval_harness.judge import (
    JUDGE_SCALE,
    JudgeVerdict,
    build_evidence,
    build_judge_messages,
    derive_cell_outcome,
)
from skills_eval_harness.models import AnalysisPlan, Suite
from skills_eval_harness.provenance import Provenance, seal_run
from skills_eval_harness.results import summarize_cells, trial_evidence
from skills_eval_harness.source import materialize_git_identity, write_git_commit_object

BundleKind = Literal["absolute", "paired"]
BundleMutation = Literal[
    "config-model",
    "config-reasoning",
    "provenance-source-commit",
    "provenance-skill-digest",
    "suite-role",
    "summary-analysis",
    "cell-evidence",
    "cell-verdict",
]


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


def _build_absolute_bundle(tmp_path: Path) -> tuple[Path, Path]:
    """Build one complete production bundle without invoking Harbor, a worker, or a judge."""
    root = tmp_path / "publication-repository"
    root.mkdir()
    git(root, "init", "-q")
    git(
        root,
        "remote",
        "add",
        "origin",
        "https://github.com/acme/evaluation-reports.git",
    )
    run = root / "run"
    inputs = run / "inputs"
    inputs.mkdir(parents=True)

    runtime = inputs / "runtime"
    runtime.write_bytes(b"deterministic offline runtime\n")
    runtime_digest = sha256_file(runtime)
    image_digest = "1" * 64
    verifier_digest = "2" * 64
    suite = {
        "schema_version": 1,
        "id": "offline-suite",
        "kind": "absolute",
        "default_samples": 1,
        "scenarios": ["offline-read"],
        "arms": [{"id": "ordinary", "skill": False, "role": None}],
    }
    config_text = f"""schema_version: 1
harbor_version: 0.21.0
container:
  image: verifier@sha256:{verifier_digest}
  agent_image: agent
  agent_image_id: sha256:{image_digest}
  cpus: 1
  memory_mb: 256
  storage_mb: 1024
  node_version: 22.23.2
  network_mode: allowlist
  agent_hosts: {{codex: []}}
  verifier_network_mode: no-network
agents:
  codex: {{harbor_name: codex, model: offline-model, version: 0.147.0, credential_env: OPENAI_API_KEY, reasoning: medium}}
  claude: {{harbor_name: claude-code, model: offline-model, version: 2.1.233, credential_env: ANTHROPIC_API_KEY, reasoning: medium}}
judge: {{model: offline-judge, credential_env: OPENAI_API_KEY, reasoning: low, timeout_seconds: 1, concurrency: 1}}
execution: {{timeout_seconds: 1, global_concurrency: 1, retries: 0}}
runtimes: {{0.18.0: {runtime_digest}}}
skill_repositories: [https://github.com/acme/skills]
"""
    catalog_text = """schema_version: 2
scenarios:
  - id: offline-read
    fixture: demo-fixture
    command_families: [read]
    procedure: Read the fixture fact.
    excellent: Report the fixture fact exactly.
    postconditions:
      - type: unchanged_except
        values: []
"""
    suite_text = """schema_version: 1
id: offline-suite
kind: absolute
default_samples: 1
scenarios: [offline-read]
arms:
  - {id: ordinary, skill: false, role: null}
"""
    fixture_registry = {
        "demo": {"repository": "https://github.com/acme/demo-fixture", "commit": ""}
    }

    source_repository = tmp_path / "source-repository"
    source_commit = commit_repository(
        source_repository,
        {
            "skills/demo/SKILL.md": "---\nname: demo\nmetadata:\n  version: '1.0.0'\n---\noffline skill\n"
        },
        "https://github.com/acme/skills.git",
    )
    harness_repository = tmp_path / "harness-repository"
    harness_commit = commit_repository(
        harness_repository,
        {
            "evals/config.yaml": config_text,
            "evals/scenarios/iwe.yaml": catalog_text,
            "evals/fixtures/sources.json": "placeholder\n",
            "evals/suites/offline.yaml": suite_text,
        },
        "https://github.com/acme/harness.git",
    )
    fixture_repository = tmp_path / "fixture-repository"
    fixture_commit = commit_repository(
        fixture_repository,
        {"fact.txt": "the fixture fact\n"},
        "https://github.com/acme/demo-fixture.git",
    )
    fixture_registry["demo"]["commit"] = fixture_commit
    fixture_text = json.dumps(fixture_registry, sort_keys=True) + "\n"
    (harness_repository / "evals/fixtures/sources.json").write_text(fixture_text)
    git(harness_repository, "add", "evals/fixtures/sources.json")
    git(
        harness_repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "registry",
    )
    harness_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=harness_repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    materialize_git_identity(
        source_repository, inputs / "source-repository", inputs / "source-commit-object"
    )
    materialize_git_identity(
        harness_repository,
        inputs / "harness-repository",
        inputs / "harness-commit-object",
    )
    shutil.copytree(inputs / "source-repository/skills/demo", inputs / "selected-skill")
    shutil.copytree(
        fixture_repository,
        inputs / "fixtures/demo",
        ignore=shutil.ignore_patterns(".git"),
    )
    shutil.copytree(
        inputs / "fixtures/demo", inputs / "materialized-fixtures/demo-fixture"
    )
    write_git_commit_object(fixture_repository, inputs / "fixture-commit-objects/demo")
    (inputs / "config.yaml").write_text(config_text)
    (inputs / "scenario-catalog.yaml").write_text(catalog_text)
    (inputs / "suite.yaml").write_text(suite_text)
    atomic_write_json(inputs / "effective-suite.json", suite)
    (inputs / "fixture-sources.json").write_text(fixture_text)

    task = run / "datasets/ordinary/offline-read--sample-001"
    (task / "tests").mkdir(parents=True)
    (task / "task.toml").write_text("version = '1.0'\n")
    (task / "instruction.md").write_text("Read the fixture fact.\n")
    (task / "tests/verify.py").write_text("print('offline')\n")
    (task / "tests/before-tree.json").write_text(
        json.dumps(
            [
                {
                    "path": "fact.txt",
                    "sha256": sha256_file(
                        inputs / "materialized-fixtures/demo-fixture/fact.txt"
                    ),
                }
            ]
        )
    )
    task_digest = harbor_content_sha256(
        task, virtual_files={"environment/payload/usr/local/bin/iwe": runtime}
    )

    fixture_tree = git_tree_sha1(inputs / "fixtures/demo")
    provenance = Provenance(
        source_url=f"https://github.com/acme/skills/tree/{source_commit}/skills/demo",
        source_commit=source_commit,
        source_tree_sha256=sha256_tree(inputs / "source-repository"),
        selected_skill="demo",
        selected_skill_sha256=sha256_tree(inputs / "selected-skill"),
        selected_skill_harbor_sha256=harbor_skill_sha256(inputs / "selected-skill"),
        runtime_version="0.18.0",
        runtime_sha256=runtime_digest,
        harness_commit=harness_commit,
        harness_tree_sha256=sha256_tree(inputs / "harness-repository"),
        harness_dirty=False,
        suite_sha256=sha256_file(inputs / "suite.yaml"),
        effective_suite_sha256=sha256_file(inputs / "effective-suite.json"),
        scenario_catalog_sha256=sha256_file(inputs / "scenario-catalog.yaml"),
        config_sha256=sha256_file(inputs / "config.yaml"),
        fixture_registry_sha256=sha256_file(inputs / "fixture-sources.json"),
        harbor_version="0.21.0",
        node_version="22.23.2",
        agent_versions={"codex": "0.147.0", "claude": "2.1.233"},
        task_checksums={"ordinary/offline-read--sample-001": task_digest},
        image_digests={"agent": image_digest, "verifier": verifier_digest},
        fixture_sources={
            "demo": {
                "repository": "https://github.com/acme/demo-fixture",
                "commit": fixture_commit,
                "tree": fixture_tree,
                "payload_sha256": sha256_tree(inputs / "fixtures/demo"),
            }
        },
        worker_auth_mode="api-key",
        judge_auth_mode="api-key",
        judge_concurrency=1,
    )
    (run / "provenance.json").write_text(provenance.model_dump_json())

    trial_name = "offline-trial"
    trial_dir = run / "jobs/ordinary" / trial_name
    (trial_dir / "agent").mkdir(parents=True)
    (trial_dir / "verifier").mkdir()
    (trial_dir / "agent/trajectory.json").write_text(
        json.dumps({"steps": [{"source": "agent", "message": "the fixture fact"}]})
    )
    oracle = {
        "procedure": "Read the fixture fact.",
        "excellent": "Report the fixture fact exactly.",
        "source_excerpts": [
            {
                "path": "fact.txt",
                "sha256": sha256_file(
                    inputs / "materialized-fixtures/demo-fixture/fact.txt"
                ),
                "text": "the fixture fact",
            }
        ],
        "relationships": {},
    }
    (trial_dir / "verifier/oracle.json").write_text(json.dumps(oracle, sort_keys=True))
    (trial_dir / "verifier/mechanical.json").write_text(json.dumps({"failures": []}))
    (trial_dir / "verifier/workspace-manifest.json").write_text("[]")
    (trial_dir / "verifier/test-stdout.txt").write_text("offline verification passed\n")
    (trial_dir / "verifier/test-stderr.txt").write_text("")
    trial = TrialResult.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "task_name": "iwe/offline-read--sample-001",
            "trial_name": trial_name,
            "trial_uri": "file:///offline-trial",
            "task_id": {"path": "/offline-task"},
            "task_checksum": task_digest,
            "config": {"task": {"name": "iwe/offline-read--sample-001"}},
            "agent_info": {"name": "codex", "version": "0.147.0"},
            "agent_result": {
                "n_input_tokens": 10,
                "n_cache_tokens": 2,
                "n_output_tokens": 3,
                "cost_usd": 0.01,
            },
            "verifier_result": {"rewards": {"infrastructure": 1}},
            "verifier_environment_mode": "separate",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
        }
    )
    atomic_write_json(
        trial_dir / "result.json", trial.model_dump(mode="json", exclude_none=True)
    )
    job = JobResult.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "n_total_trials": 1,
            "stats": {"n_completed_trials": 1, "evals": {}},
        }
    )
    atomic_write_json(
        run / "jobs/ordinary/result.json",
        job.model_dump(mode="json", exclude_none=True),
    )
    lock_trial = {
        "schema_version": 2,
        "install_only": False,
        "timeout_multiplier": 1.0,
        "agent": {
            "name": "codex",
            "model_name": "offline-model",
            "skills": [],
            "resume_trajectory": False,
            "extra_allowed_hosts": [],
            "kwargs": {"version": "0.147.0", "reasoning_effort": "medium"},
            "mcp_servers": [],
        },
        "skills": [],
        "environment": {
            "type": "docker",
            "force_build": False,
            "delete": True,
            "cpu_enforcement_policy": "auto",
            "memory_enforcement_policy": "auto",
            "extra_docker_compose": [],
            "kwargs": {},
            "extra_allowed_hosts": [],
        },
        "verifier": {"disable": False, "environment_mode": "separate"},
        "task": {
            "name": "offline-read--sample-001",
            "source": "ordinary",
            "digest": f"sha256:{task_digest}",
        },
    }
    atomic_write_json(
        run / "jobs/ordinary/lock.json",
        {
            "schema_version": 3,
            "harbor": {"version": "0.21.0", "is_editable": False},
            "n_concurrent_trials": 1,
            "retry": {"max_retries": 0},
            "trials": [lock_trial],
        },
    )

    scenario = scenario_map(inputs / "scenario-catalog.yaml")["offline-read"]
    evidence = build_evidence(trial_evidence(run / "jobs/ordinary", trial_name))
    verdict = {
        "rationale": "All deterministic offline evidence supports the result.",
        "dimensions": {
            name: {
                "score": 5,
                "rationale": "Deterministic evidence supports this score.",
                "evidence_ids": ["E0003"],
            }
            for name in (
                "task_correctness",
                "scenario_compliance",
                "skill_compliance",
                "safety",
                "evidence_quality",
                "tool_efficiency",
                "resource_efficiency",
            )
        },
    }
    scores, passed, required = derive_cell_outcome(
        JudgeVerdict.model_validate(verdict),
        role=None,
        agent="codex",
    )
    cell = {
        "arm": "ordinary",
        "scenario_id": "offline-read",
        "family": "read",
        "sample": 1,
        "valid": True,
        "pass": passed,
        "required_pass": required,
        "scenario_outcome": "passed",
        "scenario_failures": [],
        "scores": scores,
        "wall_time_seconds": 1.0,
        "n_input_tokens": 10,
        "n_cache_tokens": 2,
        "n_output_tokens": 3,
        "cost_usd": 0.01,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "judge_messages": build_judge_messages(
            scenario=scenario, evidence=evidence, scale=JUDGE_SCALE
        ),
        "verdict": verdict,
    }
    atomic_write_json(run / "cells/ordinary--offline-read--1.json", cell)
    validated_suite = Suite.model_validate(suite)
    summary = summarize_cells(
        [cell],
        {("ordinary", "offline-read", 1)},
        expected_families={"offline-read": "read"},
        analysis=AnalysisPlan.from_suite(
            validated_suite, families={"offline-read": "read"}, samples=1
        ),
        pipeline_elapsed_seconds=1.5,
        run_purpose="production",
        samples_per_identity=1,
        preregistered_samples=1,
    )
    atomic_write_json(run / "summary.json", summary)
    atomic_write_json(
        run / "run-manifest.json",
        {
            "schema_version": 1,
            "run_id": "offline-current-v6",
            "run_purpose": "production",
            "agent": "codex",
            "agent_version": "0.147.0",
            "node_version": "22.23.2",
            "worker_auth_mode": "api-key",
            "judge_auth_mode": "api-key",
            "evidence_protocol": "judge-evidence-v3",
            "samples": 1,
            "suite_default_samples": 1,
            "suite": suite,
            "suite_repository_path": "evals/suites/offline.yaml",
            "datasets": {"ordinary": "datasets/ordinary"},
            "execution": {
                "global_concurrency": 1,
                "judge_concurrency": 1,
                "arm_concurrency_batches": [{"ordinary": 1}],
            },
        },
    )
    atomic_write_json(
        run / "device-telemetry.json",
        {
            "schema_version": 2,
            "started_unix_ms": 1000,
            "finished_unix_ms": 2000,
            "host": {
                "logical_cpus": 1,
                "total_memory_bytes": 4096,
                "total_swap_bytes": 0,
                "docker_metrics_available": False,
                "telemetry_scope": "whole-host",
                "network_scope": "default-route-interfaces",
                "disk_scope": "physical-block-devices",
                "filesystem_scope": "root-filesystem",
            },
            "samples": [
                {
                    "elapsed_ms": 0,
                    "cpu_percent": 0.0,
                    "load1": 0.0,
                    "mem_available_bytes": 2048,
                    "swap_free_bytes": 0,
                    "running_containers": 0,
                    "network_rx_bytes": 0,
                    "network_tx_bytes": 0,
                    "disk_read_bytes": 0,
                    "disk_write_bytes": 0,
                    "rootfs_used_bytes": 1024,
                    "rootfs_free_bytes": 2048,
                    "network_rx_bytes_per_second": 0.0,
                    "network_tx_bytes_per_second": 0.0,
                    "disk_read_bytes_per_second": 0.0,
                    "disk_write_bytes_per_second": 0.0,
                }
            ],
            "peaks": {
                "cpu_percent": 0.0,
                "load1": 0.0,
                "running_containers": 0,
                "network_rx_bytes_per_second": 0.0,
                "network_tx_bytes_per_second": 0.0,
                "disk_read_bytes_per_second": 0.0,
                "disk_write_bytes_per_second": 0.0,
                "rootfs_used_bytes": 1024,
            },
            "minima": {
                "mem_available_bytes": 2048,
                "swap_free_bytes": 0,
                "rootfs_free_bytes": 2048,
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
        },
    )
    seal_run(run)
    return root, run


def _convert_to_paired(tmp_path: Path, root: Path, run: Path) -> tuple[Path, Path]:
    """Convert the canonical absolute fixture into a two-arm paired fixture."""
    suite = {
        "schema_version": 1,
        "id": "offline-paired-suite",
        "kind": "paired",
        "default_samples": 1,
        "scenarios": ["offline-read"],
        "arms": [
            {"id": "control", "skill": False, "role": "control"},
            {"id": "treatment", "skill": True, "role": "treatment"},
        ],
    }
    suite_text = json.dumps(suite, sort_keys=True, indent=2) + "\n"
    inputs = run / "inputs"
    (inputs / "suite.yaml").write_text(suite_text)
    atomic_write_json(inputs / "effective-suite.json", suite)

    harness_repository = tmp_path / "harness-repository"
    (harness_repository / "evals/suites/offline.yaml").write_text(suite_text)
    git(harness_repository, "add", "evals/suites/offline.yaml")
    git(
        harness_repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "paired suite",
    )
    shutil.rmtree(inputs / "harness-repository")
    materialize_git_identity(
        harness_repository,
        inputs / "harness-repository",
        inputs / "harness-commit-object",
    )

    ordinary_dataset = run / "datasets/ordinary"
    ordinary_job = run / "jobs/ordinary"
    ordinary_cell = json.loads(
        (run / "cells/ordinary--offline-read--1.json").read_text()
    )
    task_digest = harbor_content_sha256(
        ordinary_dataset / "offline-read--sample-001",
        virtual_files={"environment/payload/usr/local/bin/iwe": inputs / "runtime"},
    )
    cells = []
    for arm, skill_enabled in (("control", False), ("treatment", True)):
        shutil.copytree(ordinary_dataset, run / f"datasets/{arm}")
        shutil.copytree(ordinary_job, run / f"jobs/{arm}")
        lock_path = run / f"jobs/{arm}/lock.json"
        lock = json.loads(lock_path.read_text())
        trial = lock["trials"][0]
        trial["task"]["source"] = arm
        if skill_enabled:
            trial["agent"]["skills"] = ["/deterministic/offline/demo"]
            trial["skills"] = [
                {
                    "name": "demo",
                    "digest": f"sha256:{harbor_skill_sha256(inputs / 'selected-skill')}",
                }
            ]
        atomic_write_json(lock_path, lock)
        cell = {**ordinary_cell, "arm": arm}
        scores, passed, required = derive_cell_outcome(
            JudgeVerdict.model_validate(cell["verdict"]),
            role=arm,
            agent="codex",
        )
        cell.update({"scores": scores, "pass": passed, "required_pass": required})
        atomic_write_json(run / f"cells/{arm}--offline-read--1.json", cell)
        cells.append(cell)
    shutil.rmtree(ordinary_dataset)
    shutil.rmtree(ordinary_job)
    (run / "cells/ordinary--offline-read--1.json").unlink()

    manifest_path = run / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(
        {
            "run_id": "offline-paired-current-v5",
            "suite": suite,
            "datasets": {
                "control": "datasets/control",
                "treatment": "datasets/treatment",
            },
        }
    )
    manifest["execution"]["arm_concurrency_batches"] = [{"control": 1, "treatment": 1}]
    atomic_write_json(manifest_path, manifest)

    provenance_path = run / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance.update(
        {
            "harness_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=harness_repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "harness_tree_sha256": sha256_tree(inputs / "harness-repository"),
            "suite_sha256": sha256_file(inputs / "suite.yaml"),
            "effective_suite_sha256": sha256_file(inputs / "effective-suite.json"),
            "task_checksums": {
                "control/offline-read--sample-001": task_digest,
                "treatment/offline-read--sample-001": task_digest,
            },
        }
    )
    atomic_write_json(provenance_path, provenance)

    analysis = AnalysisPlan.from_suite(
        Suite.model_validate(suite),
        families={"offline-read": "read"},
        samples=1,
    )
    summary = summarize_cells(
        cells,
        {(arm, "offline-read", 1) for arm in ("control", "treatment")},
        expected_families={"offline-read": "read"},
        analysis=analysis,
        pipeline_elapsed_seconds=1.5,
        run_purpose="production",
        samples_per_identity=1,
        preregistered_samples=1,
    )
    atomic_write_json(run / "summary.json", summary)
    seal_run(run)
    return root, run


def _apply_mutation(run: Path, mutation: BundleMutation) -> None:
    if mutation in {"config-model", "config-reasoning"}:
        path = run / "inputs/config.yaml"
        text = path.read_text()
        text = (
            text.replace("model: offline-model", "model: tampered-model", 1)
            if mutation == "config-model"
            else text.replace("reasoning: medium", "reasoning: high", 1)
        )
        path.write_text(text)
        provenance = json.loads((run / "provenance.json").read_text())
        provenance["config_sha256"] = sha256_file(path)
        atomic_write_json(run / "provenance.json", provenance)
        return
    if mutation == "provenance-source-commit":
        path = run / "provenance.json"
        payload = json.loads(path.read_text())
        payload["source_commit"] = "f" * 40
        atomic_write_json(path, payload)
        return
    if mutation == "provenance-skill-digest":
        path = run / "provenance.json"
        payload = json.loads(path.read_text())
        payload["selected_skill_sha256"] = "e" * 64
        atomic_write_json(path, payload)
        return
    if mutation == "suite-role":
        path = run / "run-manifest.json"
        payload = json.loads(path.read_text())
        payload["suite"]["arms"][0]["role"] = "treatment"
        atomic_write_json(path, payload)
        return
    if mutation == "summary-analysis":
        path = run / "summary.json"
        payload = json.loads(path.read_text())
        payload["analysis"]["absolute"] = {"forged": "arm"}
        atomic_write_json(path, payload)
        return
    cell_path = next((run / "cells").glob("*.json"))
    cell = json.loads(cell_path.read_text())
    if mutation == "cell-evidence":
        cell["evidence"][0]["text"] = "resealed forged evidence"
    else:
        cell["verdict"]["dimensions"]["task_correctness"]["score"] = 0
    atomic_write_json(cell_path, cell)


@dataclass(frozen=True)
class BundleBuilder:
    """Build deterministic sealed bundles without workers, judges, or network access."""

    root: Path
    kind: BundleKind = "absolute"
    mutations: tuple[BundleMutation, ...] = ()

    def build(self) -> tuple[Path, Path]:
        root, run = _build_absolute_bundle(self.root)
        if self.kind == "paired":
            root, run = _convert_to_paired(self.root, root, run)
        for mutation in self.mutations:
            _apply_mutation(run, mutation)
        if self.mutations:
            seal_run(run)
        return root, run
