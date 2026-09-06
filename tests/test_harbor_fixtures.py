from pathlib import Path

import pytest

from skills_eval_harness.fixtures import materialize_fixture, materialized_fixture_path


def test_core_read_fixture_materializes_expected_documents_and_schema(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "graph").mkdir(parents=True)
    (source / ".iwe").mkdir()
    (source / "graph/existing.md").write_text("# Existing\n", encoding="utf-8")
    (source / ".iwe/config.toml").write_text("[document]\n", encoding="utf-8")
    destination = tmp_path / "materialized"

    materialize_fixture(source, destination, "pkm-demo-core-read")

    assert (destination / "graph/existing.md").read_text() == "# Existing\n"
    assert "Coordinates the release." in (destination / "graph/core-alpha.md").read_text()
    assert "Records the direct implementation checklist." in (
        destination / "graph/core-beta.md"
    ).read_text()
    assert "blue-lantern handoff" in (destination / "graph/core-gamma.md").read_text()
    assert '[schemas.core]\nmatch = "core-*"' in (
        destination / ".iwe/config.toml"
    ).read_text()
    assert (destination / ".iwe/schemas/core.yaml").is_file()


def test_api_project_fixture_adds_project_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "graph").mkdir(parents=True)
    (source / "graph/api-integration.md").write_text(
        "# API Integration\n\nShip it.\n",
        encoding="utf-8",
    )
    destination = tmp_path / "materialized"

    materialize_fixture(source, destination, "pkm-demo-api-project")

    assert (destination / "graph/api-integration.md").read_text() == (
        "---\ntype: project\n---\n\n# API Integration\n\nShip it.\n"
    )


@pytest.mark.parametrize(
    ("fixture_name", "required_paths"),
    [
        (
            "pkm-demo-core-write",
            (
                "graph/core-edit.md", "graph/core-old.md", "graph/core-source.md",
                "graph/core-blocks.md", "graph/core-delete.md", "graph/core-body.md",
                "graph/core-local-text.md", "graph/core-parent.md", "graph/core-child.md",
                "graph/core-block-replace.md",
            ),
        ),
        ("pkm-demo-update", ("graph/eval-roadmap.md",)),
        ("pkm-demo-schema", (".iwe/templates/meeting.md", ".iwe/schemas/meeting.yaml")),
        ("pkm-demo-extract-inline", ("graph/eval-plan.md",)),
        ("pkm-demo-retry-code", ("src/retry.py", "tests/test_retry.py")),
    ],
)
def test_fixture_variants_materialize_required_baselines(
    tmp_path: Path, fixture_name: str, required_paths: tuple[str, ...]
) -> None:
    source = tmp_path / "source"
    (source / "graph").mkdir(parents=True)
    (source / ".iwe").mkdir()
    (source / ".iwe/config.toml").write_text("[document]\n", encoding="utf-8")

    destination = tmp_path / "materialized"
    materialize_fixture(source, destination, fixture_name)

    assert all((destination / path).is_file() for path in required_paths)
    if fixture_name == "pkm-demo-core-write":
        config = (destination / ".iwe/config.toml").read_text()
        assert "[actions.inbox]" in config
        assert 'key_template = "inbox"' in config
        assert 'document_template = """' in config
        referrer = (destination / "graph/core-referrer.md").read_text()
        assert "[Core Old](core-old.md)" in referrer
        assert "[Core Delete](core-delete.md)" in referrer
    if fixture_name == "pkm-demo-schema":
        config = (destination / ".iwe/config.toml").read_text()
        assert "[templates.meeting]" in config
        assert 'key_template = "meetings/{{slug}}"' in config
        assert "Attendees: {{ attendees }}" in config
        assert "required: [type, draft]" in (
            destination / ".iwe/schemas/meeting.yaml"
        ).read_text()


def test_unknown_fixture_variant_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="unsupported fixture variant"):
        materialize_fixture(source, tmp_path / "materialized", "pkm-demo-unknown")


def test_materialized_fixture_path_is_scoped_to_sealed_root(tmp_path: Path) -> None:
    expected = tmp_path / "inputs/materialized-fixtures/pkm-demo-core-read/graph/core-beta.md"
    assert materialized_fixture_path(
        tmp_path, "pkm-demo-core-read", "graph/core-beta.md"
    ) == expected
    with pytest.raises(ValueError, match="escapes"):
        materialized_fixture_path(tmp_path, "pkm-demo-core-read", "../../../secret")
