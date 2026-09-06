"""Static security checks for a generated Harbor dataset and launch environment."""
from __future__ import annotations

import os
import json
import shutil
import stat
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from .models import HarnessConfig

SECRET_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD")
COMMON_SECRET_NAMES = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "GH_TOKEN"}
SAFE_HOST_ENV = {"HOME", "PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"}

def selected_environment(
    config: HarnessConfig,
    agent: str,
    source: Mapping[str, str] | None = None,
    *,
    include_provider_credential: bool = True,
) -> dict[str, str]:
    source = os.environ if source is None else source
    profile = config.agents[agent]
    env = {key: source[key] for key in SAFE_HOST_ENV if key in source}
    if include_provider_credential and profile.credential_env in source:
        env[profile.credential_env] = source[profile.credential_env]
    return env


def _read_private_auth(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("Codex auth path must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Codex auth path must be a regular file")
        if info.st_uid != os.getuid():
            raise ValueError("Codex auth file must be owned by the current user")
        if info.st_mode & 0o077:
            raise ValueError("Codex auth file permissions must be 0600 or stricter")
        payload = os.read(fd, 1_048_577)
    finally:
        os.close(fd)
    if len(payload) > 1_048_576:
        raise ValueError("Codex auth file exceeds 1 MiB")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Codex auth file must contain valid JSON") from exc
    if not isinstance(document, dict) or not document:
        raise ValueError("Codex auth file must contain a non-empty JSON object")
    return payload


def validate_codex_auth(agent: str, mode: str, auth_json: str | None) -> Path | None:
    if mode == "api-key":
        if auth_json is not None:
            raise ValueError("--codex-auth-json is only valid with --codex-auth chatgpt")
        return None
    if mode != "chatgpt":
        raise ValueError(f"unknown Codex auth mode: {mode}")
    if agent != "codex":
        raise ValueError("ChatGPT subscription auth is only supported for codex")
    if auth_json is None:
        raise ValueError("--codex-auth-json is required with --codex-auth chatgpt")
    path = Path(auth_json).expanduser().absolute()
    _read_private_auth(path)
    return path.resolve()


@contextmanager
def staged_codex_auth(source: Path) -> Iterator[Path]:
    payload = _read_private_auth(source)
    directory = Path(tempfile.mkdtemp(prefix="skills-eval-auth-"))
    directory.chmod(0o700)
    target = directory / "auth.json"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        yield target
    finally:
        shutil.rmtree(directory, ignore_errors=True)

def assert_no_secret_files(task_root: Path) -> None:
    forbidden = {"auth.json", ".env", "credentials", "credentials.json", "id_rsa", "id_ed25519"}
    found = [str(path.relative_to(task_root)) for path in task_root.rglob("*") if path.is_file() and path.name in forbidden]
    if found:
        raise ValueError(f"generated task contains credential files: {sorted(found)}")


def collect_secret_needles(
    environment: Mapping[str, str],
    credential_names: set[str],
    auth_source: Path | None,
) -> tuple[bytes, ...]:
    values = {
        value.encode("utf-8")
        for name in credential_names
        if len(value := environment.get(name, "")) >= 8
    }
    if auth_source is not None:
        document = json.loads(_read_private_auth(auth_source))

        def visit(value: object, key: str = "") -> None:
            if isinstance(value, dict):
                for child_key, child in value.items():
                    visit(child, str(child_key).lower())
            elif isinstance(value, list):
                for child in value:
                    visit(child, key)
            elif isinstance(value, str) and len(value) >= 8 and any(
                marker in key for marker in ("token", "secret", "api_key", "authorization")
            ):
                values.add(value.encode("utf-8"))

        visit(document)
    return tuple(sorted(values, key=len, reverse=True))


def redact_secret_content(root: Path, needles: tuple[bytes, ...]) -> int:
    replacements = 0
    paths = (root,) if root.is_file() else tuple(sorted(item for item in root.rglob("*") if item.is_file()))
    for path in paths:
        payload = path.read_bytes()
        updated = payload
        for needle in needles:
            count = updated.count(needle)
            if count:
                replacements += count
                updated = updated.replace(needle, b"[REDACTED]")
        if updated != payload:
            path.write_bytes(updated)
    return replacements


def assert_no_secret_content(roots: tuple[Path, ...], needles: tuple[bytes, ...]) -> None:
    for root in roots:
        if not root.exists():
            continue
        paths = (root,) if root.is_file() else (item for item in root.rglob("*") if item.is_file())
        for path in paths:
            payload = path.read_bytes()
            if any(needle in payload for needle in needles):
                raise ValueError(f"credential content remains in publishable artifact: {path.name}")

def assert_symmetric_tasks(arm_roots: dict[str, Path]) -> None:
    if len(arm_roots) < 2:
        return
    normalized: dict[str, dict[str, bytes]] = {}
    for arm, root in arm_roots.items():
        files: dict[str, bytes] = {}
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            if ".git" in path.relative_to(root).parts:
                continue
            payload = path.read_bytes()
            if relative == "task.toml":
                payload = payload.replace(f'arm = "{arm}"'.encode(), b'arm = "<arm>"')
            files[relative] = payload
        normalized[arm] = files
    first_arm, first = next(iter(normalized.items()))
    for arm, value in normalized.items():
        if value != first:
            raise ValueError(f"canonical task tree differs between {first_arm} and {arm}")

def assert_symmetric_datasets(control: Path, treatment: Path) -> None:
    control_tasks = {path.name for path in control.iterdir() if path.is_dir()}
    treatment_tasks = {path.name for path in treatment.iterdir() if path.is_dir()}
    if control_tasks != treatment_tasks:
        raise ValueError("datasets are not structurally symmetric: task sets differ")
    try:
        for task in sorted(control_tasks):
            assert_symmetric_tasks({"control": control / task, "treatment": treatment / task})
    except ValueError as exc:
        raise ValueError(f"datasets are not structurally symmetric: {exc}") from exc
