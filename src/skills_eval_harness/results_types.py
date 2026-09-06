"""Cycle-free summary cell representation."""
from pydantic import ConfigDict

from .models import StrictModel


class SummaryCell(StrictModel):
    model_config = ConfigDict(extra="allow", frozen=True, strict=True)
    arm: str
    scenario_id: str
    family: str
    sample: int
    valid: bool
    scenario_outcome: str
    scenario_failures: list[str]
    invalid_reason: str | None
    scores: dict[str, float]
