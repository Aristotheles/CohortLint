"""Metadata table loading and normalization."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cohortlint.config import CohortConfig, CohortLintConfig


@dataclass(frozen=True)
class LoadedMetadata:
    cohorts: dict[str, pd.DataFrame]
    merged: pd.DataFrame


def read_table(cohort: CohortConfig) -> pd.DataFrame:
    """Read a supported table without modifying its user columns."""

    path = cohort.path
    if not path.exists():
        raise ValueError(f"Cohort file does not exist: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".tsv", ".tab"}:
            return pd.read_csv(path, sep="\t")
        if suffix in {".xlsx", ".xlsm"}:
            sheet = cohort.sheet if cohort.sheet is not None else 0
            return pd.read_excel(path, sheet_name=sheet)
    except (OSError, ValueError, ImportError) as exc:
        raise ValueError(f"Cannot read cohort {cohort.name} from {path}: {exc}") from exc
    raise ValueError(f"Unsupported metadata format: {suffix or '<none>'}")


def load_metadata(config: CohortLintConfig) -> LoadedMetadata:
    cohorts = {cohort.name: read_table(cohort) for cohort in config.cohorts}
    parts: list[pd.DataFrame] = []
    by_name = {cohort.name: cohort for cohort in config.cohorts}
    for name, frame in cohorts.items():
        normalized = frame.copy()
        normalized["__cohort__"] = name
        sample_column = by_name[name].sample_id
        if sample_column in frame.columns:
            normalized["__sample_id__"] = frame[sample_column].map(
                lambda value, cohort_name=name: None if pd.isna(value) else f"{cohort_name}:{value}"
            )
        else:
            normalized["__sample_id__"] = None
        parts.append(normalized)
    merged = pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()
    return LoadedMetadata(cohorts=cohorts, merged=merged)
