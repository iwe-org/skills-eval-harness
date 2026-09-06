"""Execute an isolated structured judge over immutable Harbor evidence."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import Future
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Generic, TypeVar, cast

from openai import OpenAI

from .judge import JUDGE_SCALE, Evidence, JudgeVerdict, build_judge_messages, validate_verdict
from .models import HarnessConfig
from .security import _read_private_auth


T = TypeVar("T")


class EquivalentJudgeCache(Generic[T]):
    """Single-flight validated judge results keyed by normalized evidence input."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._futures: dict[bytes, Future[T]] = {}

    def get_or_invoke(self, key: bytes, invoke: Callable[[], T]) -> T:
        with self._lock:
            future = self._futures.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._futures[key] = future
        if owner:
            try:
                future.set_result(invoke())
            except BaseException as exc:
                future.set_exception(exc)
                with self._lock:
                    self._futures.pop(key, None)
        return future.result()


def _retry_judge(invoke: Callable[[], T], *, max_attempts: int) -> T:
    if max_attempts < 1:
        raise ValueError("judge max_attempts must be positive")
    for attempt in range(1, max_attempts + 1):
        try:
            return invoke()
        except Exception:
            if attempt == max_attempts:
                raise
    raise AssertionError("unreachable")


def _judge_prompt(*, scenario: dict, evidence: tuple[Evidence, ...]) -> str:
    messages = build_judge_messages(
        scenario=scenario,
        evidence=evidence,
        scale=JUDGE_SCALE,
    )
    return json.dumps(
        {
            "system_instruction": messages[0]["content"],
            "evidence_envelope": json.loads(messages[1]["content"]),
            "required_action": "Return only a verdict matching the supplied JSON schema. Do not use tools.",
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _codex_judge_command(
    *,
    bwrap: Path,
    node_root: Path,
    workspace: Path,
    codex_home: Path,
    model: str,
    reasoning: str,
) -> list[str]:
    """Build a Bubblewrap-isolated Codex CLI command with no host-home mount."""
    command = [
        str(bwrap),
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--share-net",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/bin",
        "/bin",
        "--symlink",
        "usr/lib",
        "/lib",
    ]
    if Path("/usr/lib64").exists():
        command.extend(["--symlink", "usr/lib64", "/lib64"])
    command.extend(
        [
            "--dir",
            "/etc",
            "--ro-bind",
            "/etc/ssl",
            "/etc/ssl",
            "--ro-bind",
            "/etc/resolv.conf",
            "/etc/resolv.conf",
            "--ro-bind",
            "/etc/hosts",
            "/etc/hosts",
            "--ro-bind",
            "/etc/nsswitch.conf",
            "/etc/nsswitch.conf",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/home",
            "--dir",
            "/home/judge",
            "--ro-bind",
            str(node_root),
            "/opt/node",
            "--bind",
            str(workspace),
            "/work",
            "--bind",
            str(codex_home),
            "/codex-home",
            "--setenv",
            "PATH",
            "/opt/node/bin:/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/home/judge",
            "--setenv",
            "CODEX_HOME",
            "/codex-home",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "SSL_CERT_DIR",
            "/etc/ssl/certs",
            "--chdir",
            "/work",
            "/opt/node/bin/node",
            "/opt/node/lib/node_modules/@openai/codex/bin/codex.js",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "--model",
            model,
            "--output-schema",
            "/work/schema.json",
            "--output-last-message",
            "/work/verdict.json",
            "-c",
            f'model_reasoning_effort="{reasoning}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "-C",
            "/work",
            "-",
        ]
    )
    return command


def _reject_tool_events(stdout: str) -> None:
    if not stdout.strip():
        raise ValueError("Codex judge emitted empty JSONL")
    allowed_events = {"thread.started", "turn.started", "item.started", "item.completed", "turn.completed"}
    item_events = {"item.started", "item.completed"}
    allowed_items = {"reasoning", "agent_message"}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("Codex judge emitted malformed JSONL") from exc
        if not isinstance(event, dict):
            raise ValueError("Codex judge emitted malformed JSONL event")
        event_type = event.get("type")
        if event_type == "error":
            raise ValueError("Codex judge emitted an error event")
        if event_type not in allowed_events:
            raise ValueError(f"Codex judge emitted unknown event type: {event_type!r}")
        if event_type in item_events:
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise ValueError("Codex judge emitted malformed item event")
            if item["type"] not in allowed_items:
                raise ValueError(f"Codex judge attempted tool use: {item['type']!r}")
        elif "item" in event:
            raise ValueError("Codex judge emitted malformed item on a lifecycle event")


def _codex_installation() -> tuple[Path, Path]:
    bwrap_raw = shutil.which("bwrap")
    codex_raw = shutil.which("codex")
    node_raw = shutil.which("node")
    if not bwrap_raw or not codex_raw or not node_raw:
        raise RuntimeError("ChatGPT judge requires bwrap, node, and codex")
    bwrap = Path(bwrap_raw).resolve()
    codex = Path(codex_raw).resolve()
    node = Path(node_raw).resolve()
    node_root = node.parent.parent
    expected = node_root / "lib/node_modules/@openai/codex/bin/codex.js"
    if codex != expected or not expected.is_file():
        raise RuntimeError("Codex CLI must be an npm installation under the active Node runtime")
    return bwrap, node_root


def judge_cell_api(
    *,
    config: HarnessConfig,
    scenario: dict,
    evidence: tuple[Evidence, ...],
    client: OpenAI | None = None,
) -> JudgeVerdict:
    client = client or OpenAI()
    messages = build_judge_messages(
        scenario=scenario,
        evidence=evidence,
        scale=JUDGE_SCALE,
    )
    response = client.responses.create(
        model=config.judge.model,
        input=cast(Any, messages),
        reasoning={"effort": config.judge.reasoning},
        text={
            "format": {
                "type": "json_schema",
                "name": "iwe_harbor_judge_verdict",
                "strict": True,
                "schema": JudgeVerdict.model_json_schema(),
            }
        },
        timeout=config.judge.timeout_seconds,
    )
    return validate_verdict(response.output_text, evidence)


def judge_cell_chatgpt(
    *,
    config: HarnessConfig,
    scenario: dict,
    evidence: tuple[Evidence, ...],
    auth_json: Path,
) -> JudgeVerdict:
    bwrap, node_root = _codex_installation()
    payload = _read_private_auth(auth_json)
    temporary_root = Path(tempfile.mkdtemp(prefix="skills-eval-judge-"))
    temporary_root.chmod(0o700)
    workspace = temporary_root / "work"
    workspace.mkdir(mode=0o700)
    codex_home = temporary_root / "codex-home"
    codex_home.mkdir(mode=0o700)
    auth_target = codex_home / "auth.json"
    try:
        descriptor = os.open(auth_target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        (workspace / "schema.json").write_text(
            json.dumps(JudgeVerdict.model_json_schema(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        command = _codex_judge_command(
            bwrap=bwrap,
            node_root=node_root,
            workspace=workspace,
            codex_home=codex_home,
            model=config.judge.model,
            reasoning=config.judge.reasoning,
        )
        completed = subprocess.run(
            command,
            input=_judge_prompt(scenario=scenario, evidence=evidence),
            text=True,
            capture_output=True,
            timeout=config.judge.timeout_seconds,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Codex subscription judge failed with exit code {completed.returncode}")
        _reject_tool_events(completed.stdout)
        verdict_path = workspace / "verdict.json"
        if verdict_path.is_symlink() or not verdict_path.is_file() or verdict_path.stat().st_size > 1_048_576:
            raise ValueError("Codex subscription judge did not produce a bounded regular verdict")
        return validate_verdict(verdict_path.read_bytes(), evidence)
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def judge_cell(
    *,
    config: HarnessConfig,
    scenario: dict,
    evidence: tuple[Evidence, ...],
    auth_mode: str = "api-key",
    auth_json: Path | None = None,
    client: OpenAI | None = None,
) -> JudgeVerdict:
    if auth_mode == "api-key":
        if auth_json is not None:
            raise ValueError("API-key judge must not receive a Codex auth file")
        return judge_cell_api(config=config, scenario=scenario, evidence=evidence, client=client)
    if auth_mode == "chatgpt":
        if client is not None:
            raise ValueError("ChatGPT judge does not accept an OpenAI API client")
        if auth_json is None:
            raise ValueError("ChatGPT judge requires a staged Codex auth file")
        return judge_cell_chatgpt(config=config, scenario=scenario, evidence=evidence, auth_json=auth_json)
    raise ValueError(f"unknown judge auth mode: {auth_mode}")
