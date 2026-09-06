"""Validate canonical immutable fixture repositories before materialization."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class FixtureSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    repository: HttpUrl
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")


def load_fixture_sources(path: Path) -> dict[str, FixtureSource]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("fixture source registry must be a non-empty object")
    return {name: FixtureSource.model_validate(value) for name, value in raw.items()}


def fixture_source_name(fixture_name: str, sources: dict[str, FixtureSource]) -> str:
    matches = [name for name in sources if fixture_name == name or fixture_name.startswith(name + "-")]
    if len(matches) != 1:
        raise ValueError(f"fixture has no unique canonical source: {fixture_name}")
    return matches[0]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=True
    )
    return completed.stdout.strip()


def _canonical_url(value: str) -> str:
    if value.endswith(".git"):
        value = value[:-4]
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    return value


def validate_fixture_roots(
    fixtures: dict[str, str],
    required_fixture_names: set[str],
    registry_path: Path,
) -> dict[str, dict[str, str]]:
    sources = load_fixture_sources(registry_path)
    required_sources = {fixture_source_name(name, sources) for name in required_fixture_names}
    if set(fixtures) != required_sources:
        raise ValueError(f"fixture arguments must exactly match canonical sources: {sorted(required_sources)}")
    result: dict[str, dict[str, str]] = {}
    for name in sorted(required_sources):
        root = Path(fixtures[name]).resolve()
        source = sources[name]
        commit = _git(root, "rev-parse", "HEAD")
        tree = _git(root, "rev-parse", "HEAD^{tree}")
        remote = _canonical_url(_git(root, "remote", "get-url", "origin"))
        dirty = _git(root, "status", "--porcelain")
        if commit != source.commit or remote != _canonical_url(str(source.repository)) or dirty:
            raise ValueError(f"fixture source is not the clean canonical revision: {name}")
        result[name] = {"repository": _canonical_url(str(source.repository)), "commit": commit, "tree": tree}
    return result


def _write(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _materialize_api_project(root: Path) -> None:
    path = root / "graph/api-integration.md"
    path.write_text(
        "---\ntype: project\n---\n\n" + path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _materialize_core_read(root: Path) -> None:
    _write(root, "graph/core-alpha.md", "---\ntype: project\npriority: 2\n---\n\n# Core Alpha\n\nCoordinates the release.\n\n[Core Beta](core-beta.md)\n")
    _write(root, "graph/core-beta.md", "---\ntype: note\npriority: 1\n---\n\n# Core Beta\n\nRecords the direct implementation checklist.\n")
    _write(root, "graph/core-gamma.md", "---\ntype: project\npriority: 3\n---\n\n# Core Gamma\n\nTracks the higher-priority migration. The rollout uses staged cutovers and rollback checkpoints under the blue-lantern handoff.\n")
    config = root / ".iwe/config.toml"
    config.write_text(config.read_text(encoding="utf-8") + '\n[schemas.core]\nmatch = "core-*"\n', encoding="utf-8")
    _write(root, ".iwe/schemas/core.yaml", "$schema: https://document-schema.org/draft/2026-06/schema\nfrontmatter:\n  type: object\n  required: [type, priority]\n  properties:\n    type: { type: string }\n    priority: { type: number }\n")


def _materialize_core_write(root: Path) -> None:
    documents = {
        "core-edit.md": "---\ntype: note\nreviewed: false\ntemporary: true\n---\n\n# Core Edit\n\nBody must remain unchanged.\n",
        "core-old.md": "# Core Old\n\nOriginal target.\n",
        "core-source.md": "# Core Source\n\nAttach this note.\n",
        "core-blocks.md": "# Core Blocks\n\n## Keep\n\nKeep this paragraph.\n\n## Remove Me\n\nRemove this paragraph.\n\n## Tail\n\nTail remains.\n",
        "core-delete.md": "# Core Delete\n\nDeletion preview target.\n",
        "core-body.md": "---\ntype: note\nowner: Ada\n---\n\n# Core Body\n\nDraft text.\n",
        "core-local-text.md": "# Core Local Text\n\n## Deployment\n\nRuns in three regions.\n\n## Operations\n\nKeep this section.\n",
        "core-parent.md": "# Core Parent\n\nParent introduction.\n\n[Core Child](core-child.md)\n",
        "core-child.md": "# Core Child\n\nChild details.\n",
        "core-block-replace.md": "# Core Block Replace\n\n## Overview\n\nKeep overview.\n\n## Rollback\n\nUse the emergency procedure.\n\n## Tail\n\nKeep tail.\n",
        "core-referrer.md": "# Core Referrer\n\n[Core Old](core-old.md)\n\n[Core Delete](core-delete.md)\n",
    }
    for name, content in documents.items():
        _write(root, f"graph/{name}", content)
    config = root / ".iwe/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[actions.inbox]\ntype = "attach"\ntitle = "Inbox"\nkey_template = "inbox"\ndocument_template = """\n# Inbox\n\n{{content}}\n"""\n',
        encoding="utf-8",
    )


def _materialize_update(root: Path) -> None:
    _write(root, "graph/eval-roadmap.md", "# Evaluation Roadmap\n\n## Goals\n\nShip the evaluation.\n\n## Status\n\nReady for review.\n\n## Notes\n\nPreserve this section.\n")


def _materialize_schema(root: Path) -> None:
    meeting_template = "# {{ title }}\n\nAttendees: {{ attendees }}\n\n{{ body }}\n"
    _write(root, ".iwe/templates/meeting.md", meeting_template)
    _write(root, ".iwe/schemas/meeting.yaml", "$schema: https://document-schema.org/draft/2026-06/schema\nfrontmatter:\n  type: object\n  required: [type, draft]\n  properties:\n    type: { const: meeting }\n    attendees: { type: string }\n    draft: { type: boolean }\n")
    config = root / ".iwe/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[templates.meeting]\ndocument_template = """\n'
        + meeting_template
        + '"""\nkey_template = "meetings/{{slug}}"\n'
        + '\n[schemas.meeting]\nmatch = "meetings/*"\n',
        encoding="utf-8",
    )


def _materialize_extract_inline(root: Path) -> None:
    _write(root, "graph/eval-plan.md", "# Evaluation Plan\n\n## Overview\n\nPrepared plan.\n\n## Architecture\n\nUse a sealed evidence pipeline.\n\n## Delivery\n\nPublish only validated results.\n")


def _materialize_retry_code(root: Path) -> None:
    _write(root, "src/retry.py", "def retry_delays(retries: int) -> list[int]:\n    return [2 ** attempt for attempt in range(retries + 1)]\n")
    _write(root, "tests/test_retry.py", "import unittest\n\nfrom src.retry import retry_delays\n\n\nclass RetryDelayTest(unittest.TestCase):\n    def test_three_retries(self):\n        self.assertEqual(retry_delays(3), [1, 2, 4])\n\n\nif __name__ == '__main__':\n    unittest.main()\n")
    _write(root, "src/__init__.py", "")
    _write(root, "tests/__init__.py", "")


_FIXTURE_BUILDERS = {
    "pkm-demo-api-project": _materialize_api_project,
    "pkm-demo-core-read": _materialize_core_read,
    "pkm-demo-core-write": _materialize_core_write,
    "pkm-demo-update": _materialize_update,
    "pkm-demo-schema": _materialize_schema,
    "pkm-demo-extract-inline": _materialize_extract_inline,
    "pkm-demo-retry-code": _materialize_retry_code,
}
_BASE_FIXTURES = {"pkm-demo", "seventeen-centuries"}
_REQUIRED_BASELINE_PATHS = {
    "pkm-demo-core-write": tuple(f"graph/{name}" for name in (
        "core-edit.md", "core-old.md", "core-source.md", "core-blocks.md",
        "core-delete.md", "core-body.md", "core-local-text.md", "core-parent.md",
        "core-child.md", "core-block-replace.md",
    )),
    "pkm-demo-update": ("graph/eval-roadmap.md",),
    "pkm-demo-schema": (".iwe/templates/meeting.md", ".iwe/schemas/meeting.yaml"),
    "pkm-demo-extract-inline": ("graph/eval-plan.md",),
    "pkm-demo-retry-code": ("src/retry.py", "tests/test_retry.py"),
}


def validate_materialized_fixture(root: Path, fixture_name: str) -> None:
    missing = [path for path in _REQUIRED_BASELINE_PATHS.get(fixture_name, ()) if not (root / path).is_file()]
    if missing:
        raise ValueError(f"materialized fixture {fixture_name} is missing required baselines: {missing}")


def materialize_fixture(source: Path, destination: Path, fixture_name: str) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    builder = _FIXTURE_BUILDERS.get(fixture_name)
    if builder is None and fixture_name not in _BASE_FIXTURES:
        raise ValueError(f"unsupported fixture variant: {fixture_name}")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(".git"))
    if builder is not None:
        builder(destination)
    validate_materialized_fixture(destination, fixture_name)


def materialized_fixture_path(run_dir: Path, fixture_name: str, relative_path: str) -> Path:
    root = (run_dir / "inputs/materialized-fixtures").resolve()
    candidate = (root / fixture_name / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("materialized fixture path escapes the sealed fixture root") from exc
    return candidate
