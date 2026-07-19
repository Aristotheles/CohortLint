"""Validated models for ``cohortlint.yaml``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CohortConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    path: Path
    sample_id: str = Field(min_length=1)
    sheet: str | int | None = None


class SchemaColumn(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["numeric", "categorical", "ontology", "date", "string"]
    unit: str | None = None
    range: tuple[float, float] | None = None
    required: bool = False
    allowed: list[str | int | float] = Field(default_factory=list)
    synonyms: dict[str, list[str | int | float]] = Field(default_factory=dict)
    ontology: str | None = None
    role: Literal["biological", "technical"] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> SchemaColumn:
        if self.range is not None and self.range[0] > self.range[1]:
            raise ValueError("schema range minimum must not exceed maximum")
        return self


class RulesConfig(BaseModel):
    disable: list[str] = Field(default_factory=list)
    severity_overrides: dict[str, Literal["error", "warning", "info"]] = Field(
        default_factory=dict
    )
    observation_level_ratio: float = Field(default=1.5, gt=1)


class PrivacyConfig(BaseModel):
    k_anonymity_threshold: int = Field(default=5, ge=2)


class OutputConfig(BaseModel):
    lang: Literal["en", "de", "tr"] = "en"


class CohortLintConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    cohorts: list[CohortConfig] = Field(min_length=1)
    schema_: dict[str, SchemaColumn] = Field(alias="schema", min_length=1)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def unique_cohort_names(self) -> CohortLintConfig:
        names = [cohort.name for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("cohort names must be unique")
        return self

def load_config(path: Path) -> CohortLintConfig:
    """Load a config and resolve cohort paths relative to its directory."""

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Config {path} must contain a YAML mapping")
    config = CohortLintConfig.model_validate(raw)
    base = path.resolve().parent
    resolved = [
        cohort.model_copy(
            update={"path": cohort.path if cohort.path.is_absolute() else base / cohort.path}
        )
        for cohort in config.cohorts
    ]
    return config.model_copy(update={"cohorts": resolved})
