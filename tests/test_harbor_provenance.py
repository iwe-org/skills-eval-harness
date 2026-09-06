from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from skills_eval_harness.bundle import _verify_git_commit_tree, _verify_git_snapshot
from skills_eval_harness.hashing import git_tree_sha1, harbor_skill_sha256, sha256_file, sha256_tree
from skills_eval_harness.provenance import Provenance, verify_harbor_lock, verify_materialized
from skills_eval_harness.source import materialize_git_identity


def test_sealed_git_identity_binds_commit_object_and_tree(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / "file.txt").write_text("truth\n")
    subprocess.run(["git", "add", "file.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True, capture_output=True, check=True
    ).stdout.strip()
    snapshot = tmp_path / "snapshot"
    commit_object = tmp_path / "commit-object"
    materialize_git_identity(repository, snapshot, commit_object)
    _verify_git_snapshot(
        snapshot,
        commit_object,
        expected_commit=commit,
        expected_sha256=sha256_tree(snapshot),
    )
    tree = git_tree_sha1(snapshot)
    assert tree == subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repository, text=True, capture_output=True, check=True
    ).stdout.strip()
    _verify_git_commit_tree(commit_object, expected_commit=commit, expected_tree=tree)
    with pytest.raises(ValueError, match="claimed tree"):
        _verify_git_commit_tree(commit_object, expected_commit=commit, expected_tree="0" * 40)
    (snapshot / "file.txt").write_text("forged\n")
    with pytest.raises(ValueError, match="commit tree"):
        _verify_git_snapshot(
            snapshot,
            commit_object,
            expected_commit=commit,
            expected_sha256=sha256_tree(snapshot),
        )


def make_provenance(tmp_path: Path) -> tuple[Provenance, dict[str, Path]]:
    paths = {}
    for name in ("source", "skill"):
        path = tmp_path / name
        path.mkdir()
        (path / "payload").write_text(name, encoding="utf-8")
        paths[name] = path
    for name in ("runtime", "suite", "scenarios", "config"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        paths[name] = path
    provenance = Provenance(
        source_url="https://github.com/acme/skills",
        source_commit="a" * 40,
        source_tree_sha256=sha256_tree(paths["source"]),
        selected_skill="demo",
        selected_skill_sha256=sha256_tree(paths["skill"]),
        selected_skill_harbor_sha256=harbor_skill_sha256(paths["skill"]),
        runtime_version="1.2.3",
        runtime_sha256=sha256_file(paths["runtime"]),
        harness_commit="b" * 40,
        harness_tree_sha256="b" * 64,
        harness_dirty=False,
        suite_sha256=sha256_file(paths["suite"]),
        effective_suite_sha256="e" * 64,
        scenario_catalog_sha256=sha256_file(paths["scenarios"]),
        config_sha256=sha256_file(paths["config"]),
        fixture_registry_sha256=sha256_file(paths["config"]),
        harbor_version="0.21.0",
        node_version="22.23.2",
        agent_versions={"codex": "0.147.0", "claude": "2.1.233"},
        task_checksums={"arm/task": "c" * 64},
        image_digests={"agent": "d" * 64},
        fixture_sources={"fixture": {"repository": "https://github.com/acme/fixture", "commit": "f" * 40, "tree": "e" * 40, "payload_sha256": "a" * 64}},
        worker_auth_mode="api-key",
        judge_auth_mode="api-key",
        judge_concurrency=4,
    )
    return provenance, paths


def lock_for(provenance: Provenance, *, digest: str | None = None) -> dict:
    return {
        "schema_version": 3,
        "harbor": {"version": "0.21.0", "is_editable": False},
        "n_concurrent_trials": 1,
        "retry": {"max_retries": 0},
        "trials": [{
            "schema_version": 2,
            "install_only": False,
            "timeout_multiplier": 1.0,
            "agent": {
                "name": "codex",
                "model_name": "model",
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
            "task": {"name": "task", "source": "arm", "digest": "sha256:" + (digest or "c" * 64)},
        }],
    }


def verify_lock(provenance: Provenance, lock: dict) -> None:
    verify_harbor_lock(
        provenance,
        lock,
        arm_id="arm",
        n_concurrent=1,
        retries=0,
        agent_name="codex",
        agent_version="0.147.0",
        reasoning_effort="medium",
        model="model",
        skill_enabled=False,
    )

def test_materialized_bytes_and_harbor_lock_are_bound(tmp_path: Path) -> None:
    provenance, paths = make_provenance(tmp_path)
    verify_materialized(
        provenance,
        source_tree_sha256=sha256_tree(paths["source"]),
        skill_tree_sha256=sha256_tree(paths["skill"]),
        runtime=paths["runtime"],
        suite=paths["suite"],
        scenarios=paths["scenarios"],
        config=paths["config"],
    )
    verify_lock(provenance, lock_for(provenance))


def test_tampering_fails_closed(tmp_path: Path) -> None:
    provenance, paths = make_provenance(tmp_path)
    paths["runtime"].write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance mismatch"):
        verify_materialized(
            provenance,
            source_tree_sha256=sha256_tree(paths["source"]),
            skill_tree_sha256=sha256_tree(paths["skill"]),
            runtime=paths["runtime"],
            suite=paths["suite"],
            scenarios=paths["scenarios"],
            config=paths["config"],
        )
    broken = lock_for(provenance)
    broken["trials"] = []
    with pytest.raises(ValueError, match="no trials"):
        verify_lock(provenance, broken)
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_lock(provenance, lock_for(provenance, digest="f" * 64))


def test_lock_binds_execution_agent_and_skill_controls(tmp_path: Path) -> None:
    provenance, _ = make_provenance(tmp_path)
    original = lock_for(provenance)
    mutations = [
        ("n_concurrent_trials", 2),
        ("retry", {"max_retries": 9}),
        ("harbor", {"version": "0.20.0"}),
    ]
    for key, value in mutations:
        lock = deepcopy(original)
        lock[key] = value
        with pytest.raises(ValueError):
            verify_lock(provenance, lock)
    for key, value in (("name", "other"), ("model_name", "other"), ("kwargs", {"version": "0.146.0"})):
        lock = deepcopy(original)
        lock["trials"][0]["agent"][key] = value
        with pytest.raises(ValueError):
            verify_lock(provenance, lock)
    nested_mutations = (
        ("timeout_multiplier", 999),
        ("environment", {**original["trials"][0]["environment"], "type": "host"}),
        ("verifier", {"disable": False, "environment_mode": "same"}),
    )
    for key, value in nested_mutations:
        lock = deepcopy(original)
        lock["trials"][0][key] = value
        with pytest.raises(ValueError):
            verify_lock(provenance, lock)
    lock = deepcopy(original)
    lock["trials"][0]["skills"] = [{"digest": "sha256:" + provenance.selected_skill_harbor_sha256}]
    with pytest.raises(ValueError, match="unexpectedly binds"):
        verify_lock(provenance, lock)
