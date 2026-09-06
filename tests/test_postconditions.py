from pathlib import Path

import pytest

from skills_eval_harness.postconditions import evaluate_postconditions, validate_catalog_assertion


def test_catalog_validation_rejects_oversized_regex_group_before_execution() -> None:
    with pytest.raises(ValueError, match="1..8"):
        validate_catalog_assertion({"type": "response_matches_all", "values": ["x"] * 9})


def before(root: Path) -> list[dict[str, object]]:
    import hashlib
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in root.rglob("*") if path.is_file()
    ]


def test_postconditions_accept_objective_state_and_preservation(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("---\ntype: project\ndraft: false\n---\n# Status\nReady\n")
    baseline = before(tmp_path)
    note.write_text("---\ntype: project\ndraft: false\n---\n# Status\nDone\n")
    failures = evaluate_postconditions(
        root=tmp_path, before_rows=baseline, response="Updated note.md to Done.", specs=[
            {"type": "response_contains_all", "values": ["note.md", "Done"]},
            {"type": "response_matches_all", "values": [r"(?i)\bupdated\b", r"\bnote\.md\b"]},
            {"type": "frontmatter_equals", "path": "note.md", "values": {"type": "project", "draft": False}},
            {"type": "file_contains_all", "path": "note.md", "values": ["# Status", "Done"]},
            {"type": "unchanged_except", "values": ["note.md"]},
        ],
    )
    assert failures == []


def test_postconditions_reject_mechanically_plausible_wrong_state(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("---\ntype: project\n---\n# Status\nWrong\n")
    failures = evaluate_postconditions(
        root=tmp_path, before_rows=before(tmp_path), response="Done", specs=[
            {"type": "frontmatter_equals", "path": "note.md", "values": {"draft": False}},
            {"type": "file_contains_all", "path": "note.md", "values": ["Ready"]},
        ],
    )
    assert len(failures) == 2


def test_unknown_assertion_and_path_escape_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown postcondition"):
        evaluate_postconditions(root=tmp_path, before_rows=[], response="", specs=[{"type": "future"}])
    with pytest.raises(ValueError, match="invalid response regex"):
        evaluate_postconditions(root=tmp_path, before_rows=[], response="", specs=[{"type": "response_matches_all", "values": ["("]}])
    with pytest.raises(ValueError, match="relative"):
        evaluate_postconditions(root=tmp_path, before_rows=[], response="", specs=[{"type": "path_exists", "path": "/etc/passwd"}])


def test_generic_postcondition_engine_rejects_procedural_attestations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown postcondition type"):
        evaluate_postconditions(
            root=tmp_path,
            before_rows=[],
            response="",
            specs=[{"type": "targeted_fallback_read", "path": "graph/note.md"}],
        )


def test_python_unittest_does_not_require_a_path(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n")
    assert evaluate_postconditions(
        root=tmp_path, before_rows=[], response="", specs=[{"type": "python_unittest", "module": "test_ok.py"}]
    ) == []


def test_extracted_section_requires_resolving_link_and_single_moved_body(tmp_path: Path) -> None:
    source = tmp_path / "graph/eval-plan.md"
    source.parent.mkdir()
    source.write_text("# Plan\n\n## Architecture\n\nMove me.\n\n## Delivery\n\nKeep me.\n")
    baseline = before(tmp_path)
    source.write_text("# Plan\n\n[Architecture](generated.md)\n\n## Delivery\n\nKeep me.\n")
    (source.parent / "generated.md").write_text("# Architecture\n\nMove me.\n")
    spec = {"type": "extracted_section", "path": "graph/eval-plan.md", "new_pattern": "graph/*.md", "heading": "Architecture", "body": "Move me.", "source_preserves": ["## Delivery", "Keep me."]}
    assert evaluate_postconditions(root=tmp_path, before_rows=baseline, response="", specs=[spec]) == []
    source.write_text("# Plan\n\n[Architecture](missing.md)\n\n## Architecture\n\nMove me.\n\n## Delivery\n\nKeep me.\n")
    assert len(evaluate_postconditions(root=tmp_path, before_rows=baseline, response="", specs=[spec])) == 1
