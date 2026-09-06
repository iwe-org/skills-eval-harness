"""Strict typed schema-v6 summary contract."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from .models import StrictModel
from .results_types import SummaryCell


class SummaryModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AnalysisSummary(SummaryModel):
    kind: Literal["absolute", "paired"]
    absolute: dict[str, str] | None
    paired: dict[str, str] | None


class AcceptanceStatus(SummaryModel):
    applicable: bool
    passed: bool
    policy_id: Literal["dimension-sample-rate-v2"]


class ComparisonStatus(SummaryModel):
    kind: Literal["absolute", "descriptive-paired"]
    superiority_verdict: Literal["not-asserted"] | None


class EvaluationStatus(SummaryModel):
    evidence_integrity: Literal["valid", "invalid"]
    acceptance: AcceptanceStatus
    comparison: ComparisonStatus


class AcceptanceCriterion(SummaryModel):
    arm: str
    scenario_id: str
    dimension: str
    score_threshold: int
    passed_samples: int
    total_samples: int
    observed_pass_rate: float
    required_pass_rate: float
    pass_: bool = Field(alias="pass")


class AcceptanceSummary(SummaryModel):
    policy_id: Literal["dimension-sample-rate-v2"]
    score_thresholds: dict[str, int]
    sample_pass_rate_thresholds: dict[str, float]
    criteria: list[AcceptanceCriterion]
    pass_: bool = Field(alias="pass")


class ReliabilitySummary(SummaryModel):
    planned_cells_by_arm: dict[str, int]
    valid_cells_by_arm: dict[str, int]
    invalid_cells_by_arm: dict[str, int]
    completion_rate_by_arm: dict[str, float]
    invalid_reasons_by_arm: dict[str, dict[str, int]]
    scenario_failures_by_arm: dict[str, int]
    missingness_by_scenario: dict[str, dict[str, Any]]
    missingness_by_family: dict[str, dict[str, Any]]
    common_valid_pairs: int | None
    planned_pairs: int | None
    common_valid_pair_rate: float | None
    excluded_pairs: list[dict[str, Any]]


class StatisticsSummary(SummaryModel):
    available_valid: dict[str, Any]
    common_valid_paired: dict[str, Any]


class TimingSummary(SummaryModel):
    available_valid_summed_cell_seconds: float
    common_valid_summed_cell_seconds: float | None
    pipeline_elapsed_seconds: float | None


class MeasurementScope(SummaryModel):
    cell_wall_time: str
    tokens_and_cost: str
    pipeline_elapsed: str


class InterpretationSummary(SummaryModel):
    run_purpose: str
    samples_per_identity: int | None
    preregistered_samples: int | None
    inferential_status: Literal["diagnostic-only", "production-descriptive"]


class SummaryV6(SummaryModel):
    schema_version: Literal[6]
    analysis: AnalysisSummary
    expected_cells: int
    observed_cells: int
    valid: bool
    pass_: bool = Field(alias="pass")
    evaluation_status: EvaluationStatus
    acceptance: AcceptanceSummary
    reliability: ReliabilitySummary
    statistics: StatisticsSummary
    timing: TimingSummary
    measurement_scope: MeasurementScope
    interpretation: InterpretationSummary
    cells: list[SummaryCell]
