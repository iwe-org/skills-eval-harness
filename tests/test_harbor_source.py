from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from skills_eval_harness.hashing import sha256_file, sha256_tree
from skills_eval_harness.source import resolve_skill, verify_runtime


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "skills"
    skill = repo / "skills/demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n")
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "remote", "add", "origin", "https://github.com/acme/skills.git")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    return skill


def test_local_skill_binds_commit_and_bytes(tmp_path: Path) -> None:
    skill = make_repo(tmp_path)
    resolved = resolve_skill(str(skill), tmp_path / "cache")
    assert resolved.commit == git(skill, "rev-parse", "HEAD")
    assert resolved.skill_sha256 == sha256_tree(skill)
    assert resolved.repository_sha256 == sha256_tree(skill.parents[1])


def test_local_skill_ignores_untracked_ignored_bytes(tmp_path: Path) -> None:
    skill = make_repo(tmp_path)
    repository = skill.parents[1]
    (repository / ".gitignore").write_text("ignored/\n")
    git(repository, "add", ".gitignore")
    git(repository, "commit", "-m", "ignore generated files")

    before = resolve_skill(str(skill), tmp_path / "cache-before")
    ignored = repository / "ignored/generated.bin"
    ignored.parent.mkdir()
    ignored.write_bytes(b"generated and not part of HEAD")
    after = resolve_skill(str(skill), tmp_path / "cache-after")

    assert after.repository_sha256 == before.repository_sha256
    assert after.skill_sha256 == before.skill_sha256


def test_local_skill_rejects_dirty_repository(tmp_path: Path) -> None:
    skill = make_repo(tmp_path)
    (skill / "SKILL.md").write_text("changed")
    with pytest.raises(ValueError, match="clean"):
        resolve_skill(str(skill), tmp_path / "cache")


def test_runtime_version_and_hash_are_verified(tmp_path: Path) -> None:
    runtime = tmp_path / "iwe"
    runtime.write_text("#!/bin/sh\necho 'iwe 1.2.3'\n")
    runtime.chmod(0o755)
    _, digest = verify_runtime(runtime, "1.2.3")
    assert digest == sha256_file(runtime)
    with pytest.raises(ValueError, match="version mismatch"):
        verify_runtime(runtime, "9.9.9")
