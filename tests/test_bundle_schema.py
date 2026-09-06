from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from skills_eval_harness.bundle import validate_run_bundle
from skills_eval_harness.summary import SummaryV6


@pytest.mark.parametrize("schema", [1, 2, 3, 4, 5, 7, 8, None, "6", 6.0, True])
def test_validate_run_bundle_rejects_every_noncurrent_summary_schema(
    tmp_path: Path, schema: int
) -> None:
    (tmp_path / "summary.json").write_text(json.dumps({"schema_version": schema}))
    with pytest.raises(ValueError, match="only summary schema version 6"):
        validate_run_bundle(tmp_path, require_seal=False)


@pytest.mark.parametrize("payload", ["[5]", "{", "null"])
def test_validate_run_bundle_rejects_malformed_or_non_object_summary(
    tmp_path: Path, payload: str
) -> None:
    (tmp_path / "summary.json").write_text(payload)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        validate_run_bundle(tmp_path, require_seal=False)


def test_validate_run_bundle_accepts_schema_v6_at_the_schema_gate(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text(json.dumps({"schema_version": 6}))
    with pytest.raises(ValueError, match="device telemetry"):
        validate_run_bundle(tmp_path, require_seal=False)


def _summary_payload() -> dict:
    return {
        "schema_version": 6,
        "analysis": {"kind": "absolute", "absolute": {"arm": "arm"}, "paired": None},
        "expected_cells": 0,
        "observed_cells": 0,
        "valid": True,
        "pass": True,
        "evaluation_status": {
            "evidence_integrity": "valid",
            "acceptance": {"applicable": True, "passed": True, "policy_id": "dimension-sample-rate-v2"},
            "comparison": {"kind": "absolute", "superiority_verdict": None},
        },
        "acceptance": {
            "policy_id": "dimension-sample-rate-v2",
            "score_thresholds": {},
            "sample_pass_rate_thresholds": {},
            "criteria": [],
            "pass": True,
        },
        "reliability": {
            "planned_cells_by_arm": {},
            "valid_cells_by_arm": {},
            "invalid_cells_by_arm": {},
            "completion_rate_by_arm": {},
            "invalid_reasons_by_arm": {},
            "scenario_failures_by_arm": {},
            "missingness_by_scenario": {},
            "missingness_by_family": {},
            "common_valid_pairs": None,
            "planned_pairs": None,
            "common_valid_pair_rate": None,
            "excluded_pairs": [],
        },
        "statistics": {
            "available_valid": {"overall": {}, "per_scenario": {}, "per_family": {}},
            "common_valid_paired": {},
        },
        "timing": {
            "available_valid_summed_cell_seconds": 0.0,
            "common_valid_summed_cell_seconds": None,
            "pipeline_elapsed_seconds": None,
        },
        "measurement_scope": {
            "cell_wall_time": "scope",
            "tokens_and_cost": "scope",
            "pipeline_elapsed": "scope",
        },
        "interpretation": {
            "run_purpose": "production",
            "samples_per_identity": 1,
            "preregistered_samples": 1,
            "inferential_status": "production-descriptive",
        },
        "cells": [],
    }


def test_summary_v6_is_independent_of_dictionary_insertion_order() -> None:
    payload = _summary_payload()
    reversed_payload = dict(reversed(tuple(payload.items())))
    assert SummaryV6.model_validate(payload) == SummaryV6.model_validate(
        reversed_payload
    )
    assert (
        SummaryV6.model_validate(payload).model_dump_json()
        == SummaryV6.model_validate(reversed_payload).model_dump_json()
    )



@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("expected_cells",), "0"),
        (("valid",), 1),
        (("analysis", "absolute"), []),
        (("timing", "available_valid_summed_cell_seconds"), "0"),
        (("interpretation", "samples_per_identity"), 1.0),
    ],
)
def test_summary_v6_rejects_malformed_nested_types(
    path: tuple[str, ...], value: object
) -> None:
    payload = _summary_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        SummaryV6.model_validate(payload)


@pytest.mark.parametrize(
    "section", [None, "analysis", "evaluation_status", "reliability", "timing"]
)
def test_summary_v6_rejects_extra_fields_at_every_level(section: str | None) -> None:
    payload = _summary_payload()
    target = payload if section is None else payload[section]
    target["unexpected"] = "must fail closed"
    with pytest.raises(ValidationError):
        SummaryV6.model_validate(payload)
