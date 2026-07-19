"""Core immutable data passed between CohortLint rules and reporters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    severity: Severity
    cohort: str | None = None
    column: str | None = None
    message_params: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggestion_params: dict[str, Any] = Field(default_factory=dict)


class Report(BaseModel):
    findings: list[Finding]
    cohorts: list[str]
    n_samples: dict[str, int]
    integrability_score: float = Field(ge=0, le=100)
    generated_at: datetime
    cohortlint_version: str


class RuleContext(BaseModel):
    """Read-only inputs supplied to every rule."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    cohorts: dict[str, pd.DataFrame]
    merged: pd.DataFrame
    config: Any
