"""Generate deterministic cohort tables with tagged structural defects."""

from pathlib import Path

import pandas as pd


def generate_structural_fixture(directory: Path) -> Path:
    """Write a fixture that triggers S001, S002, S003 and S004 exactly once each."""

    first = directory / "first.csv"
    second = directory / "second.tsv"
    pd.DataFrame({"id": ["a1", "a1"], "age": [20, 21], "sex": ["f", "f"]}).to_csv(
        first, index=False
    )
    pd.DataFrame({"id": ["b1", "b2"], "age": ["bad", "30"]}).to_csv(
        second, sep="\t", index=False
    )
    config = directory / "cohortlint.yaml"
    config.write_text(
        f"""version: 1
cohorts:
  - {{name: first, path: '{first.as_posix()}', sample_id: id}}
  - {{name: second, path: '{second.as_posix()}', sample_id: id}}
schema:
  age: {{type: numeric}}
  sex: {{type: categorical}}
""",
        encoding="utf-8",
    )
    return config
