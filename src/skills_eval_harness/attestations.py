"""Privacy-preserving procedural attestations from private trajectories."""
from __future__ import annotations

import ast
import json
import re
import shlex
from decimal import Decimal
from typing import Any

_CMD = re.compile(r'cmd:"((?:\\.|[^"\\])*)"')
_COMPLETION = re.compile(
    r"Script completed\nWall time ((?:0|[1-9]\d*)(?:\.\d{1,3})?) seconds\nOutput:\n"
)
_UNAVAILABLE_RESULT = {"type": "input_text", "text": "iwe: unavailable in this scenario\n"}


def _is_controlled_unavailable(observation: str | None) -> bool:
    if not isinstance(observation, str) or len(observation) > 512:
        return False
    try:
        parsed = ast.literal_eval(observation)
    except (SyntaxError, ValueError):
        return False
    if not isinstance(parsed, list) or len(parsed) != 2 or parsed[1] != _UNAVAILABLE_RESULT:
        return False
    metadata = parsed[0]
    if not isinstance(metadata, dict) or set(metadata) != {"type", "text"}:
        return False
    if metadata.get("type") != "input_text" or not isinstance(metadata.get("text"), str):
        return False
    match = _COMPLETION.fullmatch(metadata["text"])
    return match is not None and Decimal(match.group(1)) <= Decimal(300)


def _command_rows(document: dict[str, Any]) -> list[tuple[list[str] | None, str | None]]:
    rows: list[tuple[list[str] | None, str | None]] = []
    for step in document.get("steps", []):
        if not isinstance(step, dict) or step.get("source") != "agent":
            continue
        results = (step.get("observation") or {}).get("results", [])
        observations = {
            result.get("source_call_id"): result.get("content")
            for result in results
            if isinstance(result, dict)
            and isinstance(result.get("source_call_id"), str)
            and isinstance(result.get("content"), str)
        }
        for call in step.get("tool_calls") or []:
            arguments = call.get("arguments") if isinstance(call, dict) else None
            source = arguments.get("input") if isinstance(arguments, dict) else None
            match = _CMD.search(source) if isinstance(source, str) else None
            call_id = call.get("tool_call_id") if isinstance(call, dict) else None
            observation = observations.get(call_id)
            if match is None:
                rows.append((None, observation))
                continue
            try:
                argv = shlex.split(json.loads(f'"{match.group(1)}"'))
            except (json.JSONDecodeError, ValueError):
                argv = None
            rows.append((argv, observation))
    return rows


def _commands(document: dict[str, Any]) -> list[list[str] | None]:
    return [argv for argv, _ in _command_rows(document)]


def _is_targeted_read(argv: list[str], target: str) -> bool:
    if not argv or argv[-1] != target:
        return False
    if argv[0] == "cat":
        return argv == ["cat", target]
    if argv[0] in {"head", "tail"}:
        return all(not value.startswith("-") or value.lstrip("-n").isdigit() for value in argv[1:-1])
    if argv[0] == "sed":
        return len(argv) == 4 and argv[1] == "-n" and argv[2].endswith("p")
    if argv[0] == "awk" and len(argv) == 3:
        program = argv[1]
        forbidden = ("system", "getline", "\x00")
        redirect = re.search(r"\bprint(?:f)?\b[^;{}]*[<>]", program)
        io_pipe = "|" in program.replace("||", "")
        return (
            len(program) <= 256
            and redirect is None
            and not io_pipe
            and not any(item in program.lower() for item in forbidden)
        )
    return False


def fallback_attestation(document: dict[str, Any], target: str) -> dict[str, Any]:
    rows = _command_rows(document)
    commands = [argv for argv, _ in rows]
    iwe_indices = [index for index, argv in enumerate(commands) if argv and argv[:2] == ["iwe", "retrieve"]]
    reads = [index for index, argv in enumerate(commands) if argv and _is_targeted_read(argv, target)]
    observation = rows[iwe_indices[0]][1] if len(iwe_indices) == 1 else None
    unavailable = _is_controlled_unavailable(observation)
    after_attempt = bool(unavailable and reads and reads[0] > iwe_indices[0])
    unrelated = any(
        index > iwe_indices[0] and index not in reads
        for index in range(len(commands))
    ) if iwe_indices else False
    return {
        "protocol": "fallback-attestation-v4",
        "runtime_attempt_observed": len(iwe_indices) == 1,
        "runtime_unavailable_observed": unavailable,
        "targeted_fallback_observed": len(reads) == 1 and after_attempt and not unrelated,
        "declared_path": target,
        "unrelated_post_failure_tool_call_observed": unrelated,
    }
