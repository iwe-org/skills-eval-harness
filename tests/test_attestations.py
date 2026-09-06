import json

import pytest

from skills_eval_harness.attestations import fallback_attestation


def unavailable_with_wall_time(value: str) -> str:
    return repr([
        {"type": "input_text", "text": f"Script completed\nWall time {value} seconds\nOutput:\n"},
        {"type": "input_text", "text": "iwe: unavailable in this scenario\n"},
    ])


UNAVAILABLE = unavailable_with_wall_time("0.0")
TARGET = "graph/eval-roadmap.md"


def call(command: str, observation: str | None = None) -> dict:
    source = 'const r=await tools.exec_command({cmd:' + json.dumps(command) + '});'
    step = {
        "source": "agent",
        "tool_calls": [{"tool_call_id": "call-1", "arguments": {"input": source}}],
    }
    if observation is not None:
        step["observation"] = {
            "results": [{"source_call_id": "call-1", "content": observation}]
        }
    return step


def retrieve(observation: str = UNAVAILABLE) -> dict:
    return call("iwe retrieve graph/eval-roadmap.md", observation)


def test_fallback_attestation_accepts_only_one_scoped_read_after_failed_iwe() -> None:
    document = {"steps": [retrieve(), call("sed -n '1,80p' graph/eval-roadmap.md")]}
    assert fallback_attestation(document, TARGET) == {
        "protocol": "fallback-attestation-v4",
        "runtime_attempt_observed": True,
        "runtime_unavailable_observed": True,
        "targeted_fallback_observed": True,
        "declared_path": TARGET,
        "unrelated_post_failure_tool_call_observed": False,
    }


def test_fallback_attestation_fails_closed_on_broad_or_opaque_calls() -> None:
    document = {"steps": [retrieve(), call("find graph -type f"), call("cat graph/eval-roadmap.md")]}
    result = fallback_attestation(document, TARGET)
    assert result["targeted_fallback_observed"] is False
    assert result["unrelated_post_failure_tool_call_observed"] is True


def test_fallback_attestation_requires_retrieve_attempt() -> None:
    document = {"steps": [call("iwe validate graph/eval-roadmap.md"), call("cat graph/eval-roadmap.md")]}
    result = fallback_attestation(document, TARGET)
    assert result["runtime_attempt_observed"] is False
    assert result["runtime_unavailable_observed"] is False


def test_fallback_attestation_requires_controlled_unavailable_observation() -> None:
    result = fallback_attestation(
        {"steps": [retrieve("Script completed\nOutput:\n"), call("cat graph/eval-roadmap.md")]},
        TARGET,
    )
    assert result["runtime_attempt_observed"] is True
    assert result["runtime_unavailable_observed"] is False
    assert result["targeted_fallback_observed"] is False


@pytest.mark.parametrize(
    "observation",
    [
        "iwe: unavailable in this scenario\n",
        "Success: iwe: unavailable in this scenario\n",
        "Error: iwe: unavailable in this scenario\ncontinued",
        unavailable_with_wall_time("300.001"),
        unavailable_with_wall_time("1e2"),
        unavailable_with_wall_time("nan"),
        repr([
            {"type": "input_text", "text": "Script completed\nWall time 0.0 seconds\nOutput:\n"},
            {"type": "input_text", "text": "iwe: unavailable in this scenario\n"},
            {"type": "input_text", "text": "success"},
        ]),
    ],
)
def test_fallback_attestation_rejects_non_exact_unavailable_observations(observation: str) -> None:
    result = fallback_attestation(
        {"steps": [retrieve(observation), call("awk 'NR>=1 && NR<=10 {print}' graph/eval-roadmap.md")]},
        TARGET,
    )
    assert result["runtime_unavailable_observed"] is False
    assert result["targeted_fallback_observed"] is False


@pytest.mark.parametrize("wall_time", ["0", "0.0", "0.1", "1.234", "300"])
def test_fallback_accepts_bounded_wall_time_metadata(wall_time: str) -> None:
    result = fallback_attestation(
        {"steps": [retrieve(unavailable_with_wall_time(wall_time)), call("cat graph/eval-roadmap.md")]},
        TARGET,
    )
    assert result["runtime_unavailable_observed"] is True
    assert result["targeted_fallback_observed"] is True


def test_fallback_attestation_accepts_bounded_awk_regex_alternation() -> None:
    bounded = call(
        "awk 'BEGIN{capture=0} /^Status[[:space:]]*$/ || /^##+[[:space:]]+Status[[:space:]]*$/{capture=1} capture{print}' "
        "graph/eval-roadmap.md"
    )
    result = fallback_attestation({"steps": [retrieve(), bounded]}, TARGET)
    assert result["targeted_fallback_observed"] is True
    assert result["unrelated_post_failure_tool_call_observed"] is False


def test_fallback_attestation_rejects_awk_escape_and_shell_pipeline() -> None:
    escaped = call("awk 'BEGIN{print 1 > \"/tmp/leak\"}' graph/eval-roadmap.md")
    piped = call("awk '{print}' graph/eval-roadmap.md | head -1")
    for read in (escaped, piped):
        result = fallback_attestation({"steps": [retrieve(), read]}, TARGET)
        assert result["targeted_fallback_observed"] is False
        assert result["unrelated_post_failure_tool_call_observed"] is True