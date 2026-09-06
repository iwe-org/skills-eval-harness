import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from skills_eval_harness.cli import (
    _arm_concurrency_batches,
    _codex_auth_args,
    _required_credentials,
    _resolve_global_concurrency,
    _resolve_judge_concurrency,
    _run_concurrently_in_order,
    _scenario_family,
    parser,
    prepare,
    verify_agent_image,
)
from skills_eval_harness.dataset import scenario_map
from skills_eval_harness.models import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_production_clean_tree_guard_precedes_skill_cache_resolution() -> None:
    source = inspect.getsource(prepare)
    assert source.index("commit, dirty = _clean_git()") < source.index("source = resolve_skill(")


def test_codex_auth_cli_supports_api_key_and_explicit_chatgpt_modes(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parser().parse_args(["run", "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--codex-auth {api-key,chatgpt}" in help_text
    assert "--codex-auth-json" in help_text
    assert "--judge-auth {api-key,chatgpt}" in help_text
    assert "--jobs JOBS" in help_text
    assert "--judge-jobs JUDGE_JOBS" in help_text


def test_publish_evidence_is_opt_in() -> None:
    without_evidence = parser().parse_args(["publish", "run", "report.md"])
    with_evidence = parser().parse_args(["publish", "run", "report.md", "--include-evidence"])
    assert without_evidence.include_evidence is False
    assert with_evidence.include_evidence is True


def test_global_concurrency_defaults_to_two_and_can_be_overridden() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    args = parser().parse_args([
        "run", "--suite", "suite.yaml", "--skill-source", "skill", "--runtime", "iwe",
        "--runtime-version", "0.18.0", "--fixture", "fixture=.", "--output", "out",
    ])
    assert config.execution.global_concurrency == 2
    assert args.jobs is None
    assert _resolve_global_concurrency(args.jobs, config) == 2
    assert _resolve_global_concurrency(6, config) == 6
    with pytest.raises(ValueError, match="global concurrency"):
        _resolve_global_concurrency(0, config)


def test_judge_concurrency_defaults_to_four_and_can_be_overridden() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    args = parser().parse_args([
        "run", "--suite", "suite.yaml", "--skill-source", "skill", "--runtime", "iwe",
        "--runtime-version", "0.18.0", "--fixture", "fixture=.", "--output", "out",
    ])
    assert config.judge.concurrency == 4
    assert args.judge_jobs is None
    assert _resolve_judge_concurrency(args.judge_jobs, config) == 4
    assert _resolve_judge_concurrency(7, config) == 7
    with pytest.raises(ValueError, match="judge concurrency"):
        _resolve_judge_concurrency(0, config)


def test_concurrent_judging_is_bounded_and_preserves_input_order() -> None:
    import threading
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    def work(value: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02 * (4 - value))
        with lock:
            active -= 1
        return value * 10

    assert _run_concurrently_in_order([1, 2, 3], 2, work) == [10, 20, 30]
    assert peak == 2


def test_global_concurrency_is_balanced_across_paired_arms() -> None:
    assert _arm_concurrency_batches(("skill", "no-skill"), 4) == (
        {"skill": 2, "no-skill": 2},
    )
    assert _arm_concurrency_batches(("skill", "no-skill"), 5) == (
        {"skill": 2, "no-skill": 2},
    )
    assert _arm_concurrency_batches(("skill", "no-skill"), 1) == (
        {"skill": 1},
        {"no-skill": 1},
    )


def test_result_family_uses_sorted_catalog_command_families() -> None:
    scenario = scenario_map(ROOT / "evals/scenarios/iwe.yaml")["ambiguous-discovery-with-one-follow-up"]
    assert "family" not in scenario
    assert _scenario_family(scenario) == "find+retrieve"


def test_harbor_receives_only_generic_staged_auth_path() -> None:
    staged = Path("/tmp/skills-eval-auth-random/auth.json")
    assert _codex_auth_args(None) == []
    assert _codex_auth_args(staged) == [
        "--ae",
        "CODEX_AUTH_JSON_PATH=/tmp/skills-eval-auth-random/auth.json",
    ]


def test_subscription_worker_and_judge_require_no_platform_api_key() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    assert _required_credentials(config, "codex", "chatgpt", "chatgpt") == set()
    assert _required_credentials(config, "codex", "chatgpt", "api-key") == {"OPENAI_API_KEY"}
    assert _required_credentials(config, "codex", "api-key", "chatgpt") == {"OPENAI_API_KEY"}


@pytest.mark.parametrize(
    ("returncode", "image_id"),
    ((1, ""), (0, "sha256:" + "0" * 64)),
)
def test_agent_image_preflight_rejects_missing_or_wrong_id(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    image_id: str,
) -> None:
    config = load_config(ROOT / "evals/config.yaml")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=returncode, stdout=image_id)

    monkeypatch.setattr("skills_eval_harness.cli.subprocess.run", fake_run)
    with pytest.raises(ValueError, match="unavailable or has the wrong ID"):
        verify_agent_image(config)
    assert len(calls) == 1


def test_agent_image_preflight_checks_versions_after_exact_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(ROOT / "evals/config.yaml")
    responses = iter((
        SimpleNamespace(returncode=0, stdout=config.container.agent_image_id),
        SimpleNamespace(returncode=0, stdout=""),
    ))
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        commands.append(command)
        return next(responses)

    monkeypatch.setattr("skills_eval_harness.cli.subprocess.run", fake_run)
    verify_agent_image(config)
    assert commands[1][0:6] == ["docker", "run", "--rm", "--network", "none", config.container.agent_image]
    assert "node --version" in commands[1][-1]
    assert "codex --version" in commands[1][-1]
    assert "claude --version" in commands[1][-1]
