from pathlib import Path

from skills_eval_harness.models import load_suite, load_yaml


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_31_single_arm_suite_covers_the_complete_catalog_once() -> None:
    suite = load_suite(ROOT / "evals/suites/default-skill-smoke-31.yaml")
    catalog = load_yaml(ROOT / "evals/scenarios/iwe.yaml")
    assert isinstance(catalog, dict)
    catalog_ids = {item["id"] for item in catalog["scenarios"]}
    catalog_by_id = {item["id"]: item for item in catalog["scenarios"]}

    assert catalog_by_id["fix-code-without-activating-iwe"]["mutation_expected"] is True
    assert catalog_by_id["preview-one-scoped-deletion"]["mutation_expected"] is False

    assert suite.id == "default-skill-correctness-smoke-31"
    assert suite.kind == "absolute"
    assert suite.default_samples == 1
    assert len(suite.scenarios) == 31
    assert len(set(suite.scenarios)) == 31
    assert set(suite.scenarios) == catalog_ids
    assert [(arm.id, arm.role, arm.skill) for arm in suite.arms] == [
        ("skill", None, True),
    ]
