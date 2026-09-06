"""Deterministic, data-driven scenario postconditions."""
from __future__ import annotations

import fnmatch
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any, cast

EXECUTABLE_ASSERTIONS = frozenset(
    {
        "response_contains_all",
        "response_contains_ordered",
        "response_excludes_all",
        "response_matches_all",
        "path_exists",
        "path_absent",
        "file_text_exact",
        "file_contains_all",
        "file_excludes_all",
        "glob_count",
        "frontmatter_equals",
        "frontmatter_absent",
        "text_count",
        "unchanged_except",
        "python_unittest",
        "extracted_section",
    }
)
PROCEDURAL_ASSERTIONS = frozenset({"targeted_fallback_read"})
CATALOG_ASSERTIONS = EXECUTABLE_ASSERTIONS | PROCEDURAL_ASSERTIONS


def _safe_path(root: Path, relative: str) -> Path:
    if not relative or relative.startswith("/"):
        raise ValueError("postcondition path must be relative")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("postcondition path escapes workspace")
    return target


def _read_text(root: Path, relative: str) -> str:
    target = _safe_path(root, relative)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"missing bounded text file: {relative}")
    return target.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}
    block = text[4:].split("\n---\n", 1)[0]
    values: dict[str, Any] = {}
    for line in block.splitlines():
        if not line or line.startswith((" ", "-", "#")) or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip().strip('"').strip("'")
        if value in {"true", "false"}:
            values[key.strip()] = value == "true"
        elif value.isdigit():
            values[key.strip()] = int(value)
        else:
            values[key.strip()] = value
    return values


def _after_manifest(root: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if {".git", "__pycache__", ".DS_Store"} & set(relative.parts):
            continue
        if path.is_file():
            rows[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rows


def validate_catalog_assertion(spec: dict[str, Any]) -> None:
    kind = spec.get("type")
    if kind not in CATALOG_ASSERTIONS:
        raise ValueError(f"unknown postcondition type: {kind!r}")
    if kind == "response_matches_all":
        patterns = spec.get("values")
        if not isinstance(patterns, list) or not 1 <= len(patterns) <= 8:
            raise ValueError("response regex patterns must contain 1..8 items")
        if any(not isinstance(pattern, str) or not pattern or len(pattern) > 256 for pattern in patterns):
            raise ValueError("response regex patterns must be non-empty strings of at most 256 characters")
        try:
            for pattern in patterns:
                re.compile(pattern)
        except re.error as exc:
            raise ValueError("invalid response regex") from exc


def _assertion_failure(root: Path, before: dict[str, str], response: str, spec: dict[str, Any]) -> str | None:
    validate_catalog_assertion(spec)
    kind = spec.get("type")
    if kind not in EXECUTABLE_ASSERTIONS:
        raise ValueError(f"unknown postcondition type: {kind!r}")
    values = spec.get("values", [])
    path = spec.get("path")
    if path is not None and not isinstance(path, str):
        raise ValueError("postcondition path must be a string")
    bounded_path = cast(str, path)
    if kind == "response_contains_all":
        missing = [item for item in values if item not in response]
        return f"response missing {missing!r}" if missing else None
    if kind == "response_contains_ordered":
        positions = [response.find(item) for item in values]
        return None if all(position >= 0 for position in positions) and positions == sorted(positions) else "response values missing or out of order"
    if kind == "response_excludes_all":
        present = [item for item in values if item in response]
        return f"response contains forbidden {present!r}" if present else None
    if kind == "response_matches_all":
        missing = [pattern for pattern in values if re.search(pattern, response) is None]
        return f"response missing semantic patterns {missing!r}" if missing else None
    if kind == "path_exists":
        return None if _safe_path(root, bounded_path).exists() else f"path missing: {path}"
    if kind == "path_absent":
        return None if not _safe_path(root, bounded_path).exists() else f"path unexpectedly exists: {path}"
    if kind == "glob_count":
        count = sum(1 for candidate in root.rglob("*") if candidate.is_file() and fnmatch.fnmatch(candidate.relative_to(root).as_posix(), spec["pattern"]))
        return None if count == spec["count"] else f"glob count {count} != {spec['count']}"
    if kind == "unchanged_except":
        after = _after_manifest(root)
        allowed = set(values)
        changed = {item for item in set(before) | set(after) if before.get(item) != after.get(item)}
        new_globs = spec.get("new_globs", [])
        permitted_new: set[str] = set()
        for rule in new_globs:
            matches = {item for item in changed - set(before) if fnmatch.fnmatch(item, rule["pattern"])}
            if len(matches) != rule["count"]:
                return f"new path count differs for {rule['pattern']}: {len(matches)}"
            permitted_new.update(matches)
        extra = sorted(changed - allowed - permitted_new)
        return f"unexpected changed paths: {extra!r}" if extra else None
    if kind == "python_unittest":
        completed = subprocess.run(["python3", "-m", "unittest", spec["module"]], cwd=root, text=True, capture_output=True, timeout=30, check=False)
        return None if completed.returncode == 0 else f"focused unittest failed: {spec['module']}"
    if kind == "extracted_section":
        after = _after_manifest(root)
        created = sorted(
            item for item in set(after) - set(before)
            if fnmatch.fnmatch(item, spec["new_pattern"])
        )
        if len(created) != 1:
            return f"extracted section created {len(created)} candidate notes"
        source_text = _read_text(root, bounded_path)
        target_text = _read_text(root, created[0])
        heading = spec["heading"]
        body = spec["body"]
        target_name = Path(created[0]).name
        link = re.compile(rf"\[{re.escape(heading)}\]\({re.escape(target_name)}\)")
        if len(link.findall(source_text)) != 1:
            return "source does not contain exactly one resolving extraction link"
        if f"## {heading}" in source_text or body in source_text:
            return "source still contains extracted section content"
        if target_text.count(f"# {heading}") != 1 or target_text.count(body) != 1:
            return "new note does not contain extracted section exactly once"
        missing = [item for item in spec.get("source_preserves", []) if item not in source_text]
        return f"source lost preserved content: {missing!r}" if missing else None
    text = _read_text(root, bounded_path)
    if kind == "file_text_exact":
        return None if text == spec["value"] else f"file text differs: {path}"
    if kind == "file_contains_all":
        missing = [item for item in values if item not in text]
        return f"file {path} missing {missing!r}" if missing else None
    if kind == "file_excludes_all":
        present = [item for item in values if item in text]
        return f"file {path} contains forbidden {present!r}" if present else None
    if kind == "text_count":
        count = text.count(spec["value"])
        return None if count == spec["count"] else f"text count {count} != {spec['count']} in {path}"
    frontmatter = _frontmatter(text)
    if kind == "frontmatter_equals":
        wrong = {key: value for key, value in spec["values"].items() if frontmatter.get(key) != value}
        return f"frontmatter mismatch in {path}: {wrong!r}" if wrong else None
    if kind == "frontmatter_absent":
        present = sorted(set(values) & set(frontmatter))
        return f"frontmatter keys remain in {path}: {present!r}" if present else None
    raise AssertionError("unreachable")


def evaluate_postconditions(*, root: Path, before_rows: list[dict[str, Any]], response: str, specs: list[dict[str, Any]]) -> list[str]:
    before = {row["path"]: row["sha256"] for row in before_rows}
    return [failure for spec in specs if (failure := _assertion_failure(root, before, response, spec))]
