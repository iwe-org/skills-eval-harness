from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills_eval_harness.models import load_config
from skills_eval_harness.security import (
    assert_no_secret_content,
    assert_symmetric_datasets,
    collect_secret_needles,
    redact_secret_content,
    selected_environment,
    staged_codex_auth,
    validate_codex_auth,
)

ROOT = Path(__file__).resolve().parents[1]


def test_secret_content_is_redacted_before_publication(tmp_path: Path) -> None:
    secret = "sk-test-super-secret-value"
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"tokens": {"access_token": secret}}))
    auth.chmod(0o600)
    artifact = tmp_path / "jobs" / "trajectory.json"
    artifact.parent.mkdir()
    artifact.write_text(json.dumps({"output": secret}))
    needles = collect_secret_needles({}, set(), auth)
    assert redact_secret_content(artifact.parent, needles) == 1
    assert "[REDACTED]" in artifact.read_text()
    assert_no_secret_content((artifact.parent,), needles)


def test_only_selected_provider_secret_is_exposed() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    source = {"PATH": "/bin", "OPENAI_API_KEY": "openai", "ANTHROPIC_API_KEY": "anthropic", "GH_TOKEN": "github"}
    codex = selected_environment(config, "codex", source)
    claude = selected_environment(config, "claude", source)
    assert codex["OPENAI_API_KEY"] == "openai"
    assert "ANTHROPIC_API_KEY" not in codex and "GH_TOKEN" not in codex
    assert claude["ANTHROPIC_API_KEY"] == "anthropic"
    assert "OPENAI_API_KEY" not in claude and "GH_TOKEN" not in claude


def test_arm_preflight_rejects_structural_drift(tmp_path: Path) -> None:
    control = tmp_path / "control"
    treatment = tmp_path / "treatment"
    (control / "task/environment").mkdir(parents=True)
    (treatment / "task/environment").mkdir(parents=True)
    for root in (control, treatment):
        (root / "task/task.toml").write_text("same")
        (root / "task/environment/Dockerfile").write_text("same")
    assert_symmetric_datasets(control, treatment)
    (treatment / "task/task.toml").write_text("different")
    with pytest.raises(ValueError, match="not structurally symmetric"):
        assert_symmetric_datasets(control, treatment)


def test_chatgpt_auth_is_codex_only_and_requires_private_regular_json(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens":{"access_token":"secret"}}')
    auth.chmod(0o600)
    assert validate_codex_auth("codex", "chatgpt", str(auth)) == auth.resolve()
    assert validate_codex_auth("codex", "api-key", None) is None
    with pytest.raises(ValueError, match="only supported for codex"):
        validate_codex_auth("claude", "chatgpt", str(auth))
    auth.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        validate_codex_auth("codex", "chatgpt", str(auth))


def test_chatgpt_auth_rejects_symlink(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens":{"access_token":"secret"}}')
    auth.chmod(0o600)
    link = tmp_path / "linked-auth.json"
    link.symlink_to(auth)
    with pytest.raises(ValueError, match="must not be a symlink"):
        validate_codex_auth("codex", "chatgpt", str(link))


def test_chatgpt_worker_does_not_receive_platform_api_key() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    source = {"PATH": "/bin", "OPENAI_API_KEY": "platform-key"}
    env = selected_environment(config, "codex", source, include_provider_credential=False)
    assert env == {"PATH": "/bin"}


def test_auth_json_is_staged_at_generic_private_path_and_removed(tmp_path: Path) -> None:
    source = tmp_path / "auth.json"
    source.write_text('{"tokens":{"access_token":"secret"}}')
    source.chmod(0o600)
    with staged_codex_auth(source) as staged:
        assert staged.name == "auth.json"
        assert "skills-eval-auth-" in str(staged.parent)
        assert staged.read_bytes() == source.read_bytes()
        assert staged.stat().st_mode & 0o077 == 0
    assert not staged.parent.exists()


def test_staged_auth_is_removed_when_rollout_raises(tmp_path: Path) -> None:
    source = tmp_path / "auth.json"
    source.write_text('{"tokens":{"access_token":"secret"}}')
    source.chmod(0o600)
    staged_parent: Path | None = None
    with pytest.raises(RuntimeError, match="rollout failed"):
        with staged_codex_auth(source) as staged:
            staged_parent = staged.parent
            raise RuntimeError("rollout failed")
    assert staged_parent is not None
    assert not staged_parent.exists()
