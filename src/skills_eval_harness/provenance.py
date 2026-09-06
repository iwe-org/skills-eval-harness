"""Content-bound provenance records and fail-closed reconciliation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .hashing import atomic_write_json, sha256_file

SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class FixtureRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repository: str
    commit: str
    tree: str
    payload_sha256: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_url: str
    source_commit: str
    source_tree_sha256: str
    selected_skill: str
    selected_skill_sha256: str
    selected_skill_harbor_sha256: str
    runtime_version: str
    runtime_sha256: str
    harness_commit: str
    harness_tree_sha256: str
    harness_dirty: bool
    suite_sha256: str
    effective_suite_sha256: str
    scenario_catalog_sha256: str
    config_sha256: str
    fixture_registry_sha256: str
    harbor_version: Literal["0.21.0"]
    node_version: str
    agent_versions: dict[str, str]
    task_checksums: dict[str, str]
    image_digests: dict[str, str]
    fixture_sources: dict[str, FixtureRevision]
    agents_template_sha256: str | None = None
    worker_auth_mode: Literal["api-key", "chatgpt"]
    judge_auth_mode: Literal["api-key", "chatgpt"]
    judge_concurrency: int

    def validated(self) -> "Provenance":
        if not COMMIT.fullmatch(self.source_commit) or not COMMIT.fullmatch(self.harness_commit):
            raise ValueError("source and harness revisions must be full Git commits")
        if not self.fixture_sources or any(
            not COMMIT.fullmatch(value.commit) or not COMMIT.fullmatch(value.tree)
            for value in self.fixture_sources.values()
        ):
            raise ValueError("fixture revisions must bind full Git commit and tree IDs")
        hashes = (
            self.source_tree_sha256,
            self.selected_skill_sha256,
            self.selected_skill_harbor_sha256,
            self.runtime_sha256,
            self.harness_tree_sha256,
            self.suite_sha256,
            self.effective_suite_sha256,
            self.scenario_catalog_sha256,
            self.config_sha256,
            self.fixture_registry_sha256,
            *self.task_checksums.values(),
            *self.image_digests.values(),
            *(value.payload_sha256 for value in self.fixture_sources.values()),
        )
        if self.agents_template_sha256 is not None and not SHA256.fullmatch(self.agents_template_sha256):
            raise ValueError("AGENTS template digest must be lowercase SHA-256")
        if not hashes or any(not SHA256.fullmatch(value) for value in hashes):
            raise ValueError("all provenance digests must be lowercase SHA-256")
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.node_version) is None:
            raise ValueError("Node version must be an exact semantic version")
        if set(self.agent_versions) != {"codex", "claude"} or any(
            re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None
            for value in self.agent_versions.values()
        ):
            raise ValueError("agent versions must bind codex and claude to exact semantic versions")
        if not 1 <= self.judge_concurrency <= 32:
            raise ValueError("judge_concurrency must be between 1 and 32")
        return self


def verify_materialized(
    provenance: Provenance,
    *,
    source_tree_sha256: str,
    skill_tree_sha256: str,
    runtime: Path,
    suite: Path,
    scenarios: Path,
    config: Path,
) -> None:
    provenance.validated()
    actual = {
        "source_tree_sha256": source_tree_sha256,
        "selected_skill_sha256": skill_tree_sha256,
        "runtime_sha256": sha256_file(runtime),
        "suite_sha256": sha256_file(suite),
        "scenario_catalog_sha256": sha256_file(scenarios),
        "config_sha256": sha256_file(config),
    }
    expected = {key: getattr(provenance, key) for key in actual}
    mismatches = [
        f"{key}: expected {expected[key]}, got {actual[key]}"
        for key in actual
        if actual[key] != expected[key]
    ]
    if mismatches:
        raise ValueError("provenance mismatch: " + "; ".join(mismatches))


def verify_harbor_lock(
    provenance: Provenance,
    lock: dict,
    *,
    arm_id: str,
    n_concurrent: int,
    retries: int,
    agent_name: str,
    agent_version: str,
    reasoning_effort: str,
    model: str,
    skill_enabled: bool,
) -> None:
    harbor = lock.get("harbor")
    if (
        lock.get("schema_version") != 3
        or not isinstance(harbor, dict)
        or set(harbor) != {"version", "is_editable"}
        or harbor.get("version") != provenance.harbor_version
        or harbor.get("is_editable") is not False
    ):
        raise ValueError("unexpected Harbor lock schema or version")
    retry = lock.get("retry")
    if lock.get("n_concurrent_trials") != n_concurrent or not isinstance(retry, dict) or retry.get("max_retries") != retries:
        raise ValueError("Harbor lock execution controls do not match the run plan")
    trials = lock.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("Harbor lock has no trials")
    seen: set[str] = set()
    for trial in trials:
        if (
            trial.get("schema_version") != 2
            or trial.get("install_only") is not False
            or trial.get("timeout_multiplier") != 1.0
            or trial.get("verifier") != {"disable": False, "environment_mode": "separate"}
        ):
            raise ValueError("Harbor lock trial controls do not match the run plan")
        environment = trial.get("environment")
        if not isinstance(environment, dict) or environment != {
            "type": "docker",
            "force_build": False,
            "delete": True,
            "cpu_enforcement_policy": "auto",
            "memory_enforcement_policy": "auto",
            "extra_docker_compose": [],
            "kwargs": {},
            "extra_allowed_hosts": [],
        }:
            raise ValueError("Harbor lock environment controls do not match the run plan")
        if trial.get("agent", {}).get("name") != agent_name or trial.get("agent", {}).get("model_name") != model:
            raise ValueError("Harbor lock agent identity does not match the run plan")
        agent = trial["agent"]
        if (
            agent.get("resume_trajectory") is not False
            or agent.get("extra_allowed_hosts") != []
            or agent.get("kwargs") != {
                "version": agent_version,
                "reasoning_effort": reasoning_effort,
            }
            or agent.get("mcp_servers") != []
        ):
            raise ValueError("Harbor lock agent controls do not match the run plan")
        skills = trial.get("skills")
        agent_skills = agent.get("skills")
        if skill_enabled:
            if (
                not isinstance(skills, list)
                or len(skills) != 1
                or skills[0].get("name") != provenance.selected_skill
                or not isinstance(agent_skills, list)
                or len(agent_skills) != 1
                or Path(agent_skills[0]).name != provenance.selected_skill
            ):
                raise ValueError("treatment lock must bind exactly one skill")
            skill_digest = skills[0].get("digest", "")
            if skill_digest != f"sha256:{provenance.selected_skill_harbor_sha256}":
                raise ValueError("Harbor lock skill digest mismatch")
        elif skills != [] or agent_skills != []:
            raise ValueError("control or absolute no-skill lock unexpectedly binds a skill")
        task = trial.get("task") or {}
        name = task.get("name")
        source = task.get("source")
        digest = task.get("digest", "")
        key = f"{source}/{name}"
        if key in seen or key not in provenance.task_checksums:
            raise ValueError(f"unexpected or duplicate locked task: {key}")
        if not isinstance(digest, str) or not digest.startswith("sha256:") or not SHA256.fullmatch(digest.removeprefix("sha256:")):
            raise ValueError(f"invalid locked task digest: {key}")
        if digest.removeprefix("sha256:") != provenance.task_checksums[key]:
            raise ValueError(f"locked task digest mismatch: {key}")
        seen.add(key)
    expected = {key for key in provenance.task_checksums if key.split("/", 1)[0] == arm_id}
    if seen != expected:
        raise ValueError("Harbor lock is missing expected tasks")


def _publishable_files(run_dir: Path) -> dict[str, str]:
    roots = [
        run_dir / "provenance.json",
        run_dir / "run-manifest.json",
        run_dir / "summary.json",
        run_dir / "device-telemetry.json",
    ]
    for pattern in (
        "cells/*.json",
        "jobs/**/lock.json",
        "jobs/**/result.json",
        "jobs/**/trajectory.json",
        "jobs/**/oracle.json",
        "jobs/**/workspace-manifest.json",
        "jobs/**/mechanical.json",
        "jobs/**/test-stdout.txt",
        "jobs/**/test-stderr.txt",
        "inputs/**/*",
    ):
        roots.extend(
            sorted(
                path
                for path in run_dir.glob(pattern)
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            )
        )
    roots.extend(
        sorted(
            path
            for path in (run_dir / "datasets").glob("**/*")
            if path.is_file()
            and ".git" not in path.parts
            and not path.as_posix().endswith("/environment/payload/usr/local/bin/iwe")
        )
    )
    return {str(path.relative_to(run_dir)): sha256_file(path) for path in roots if path.is_file()}


def _require_complete_seal(files: dict[str, str]) -> None:
    required = {
        "provenance.json",
        "run-manifest.json",
        "summary.json",
        "device-telemetry.json",
        "inputs/config.yaml",
        "inputs/scenario-catalog.yaml",
        "inputs/suite.yaml",
        "inputs/effective-suite.json",
        "inputs/fixture-sources.json",
        "inputs/runtime",
        "inputs/source-commit-object",
        "inputs/harness-commit-object",
    }
    required_suffixes = (
        "/lock.json",
        "/result.json",
        "/trajectory.json",
        "/oracle.json",
        "/workspace-manifest.json",
        "/mechanical.json",
        "/task.toml",
        "/instruction.md",
    )
    if (
        not required.issubset(files)
        or not any(name.startswith("inputs/fixture-commit-objects/") for name in files)
        or any(not any(name.endswith(suffix) for name in files) for suffix in required_suffixes)
    ):
        raise ValueError("cannot seal incomplete run")


def seal_run(run_dir: Path) -> dict[str, object]:
    """Hash the exact complete publication payload; the seal excludes itself."""
    files = _publishable_files(run_dir)
    _require_complete_seal(files)
    seal: dict[str, object] = {"schema_version": 1, "files": files}
    atomic_write_json(run_dir / "run-seal.json", seal)
    return seal


def verify_run_seal(run_dir: Path) -> None:
    seal = json.loads((run_dir / "run-seal.json").read_text(encoding="utf-8"))
    files = seal.get("files")
    if seal.get("schema_version") != 1 or not isinstance(files, dict) or not all(
        isinstance(relative, str) and isinstance(digest, str) for relative, digest in files.items()
    ):
        raise ValueError("invalid run seal")
    _require_complete_seal(files)
    expected_files = _publishable_files(run_dir)
    if set(files) != set(expected_files):
        raise ValueError("run seal does not enumerate the exact publication payload")
    for relative, expected in files.items():
        if expected_files[relative] != expected:
            raise ValueError(f"sealed artifact mismatch: {relative}")
