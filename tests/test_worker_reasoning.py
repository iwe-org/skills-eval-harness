from pathlib import Path

import pytest

from skills_eval_harness.cli import _agent_kwargs
from skills_eval_harness.models import Agent, load_config


ROOT = Path(__file__).resolve().parents[1]


def test_worker_reasoning_is_required_and_frozen_in_config() -> None:
    config = load_config(ROOT / "evals/config.yaml")
    assert config.agents["codex"].reasoning == "medium"
    assert config.agents["claude"].reasoning == "medium"


def test_worker_reasoning_is_passed_to_harbor_agent() -> None:
    profile = Agent(
        harbor_name="codex",
        model="openai/gpt-test",
        version="0.147.0",
        credential_env="OPENAI_API_KEY",
        reasoning="medium",
    )
    assert _agent_kwargs(profile) == [
        "--ak",
        "version=0.147.0",
        "--ak",
        "reasoning_effort=medium",
    ]


def test_agent_without_reasoning_fails_current_config_validation() -> None:
    with pytest.raises(ValueError, match="reasoning"):
        Agent.model_validate({
            "harbor_name": "codex",
            "model": "openai/test",
            "version": "0.147.0",
            "credential_env": "OPENAI_API_KEY",
        })
