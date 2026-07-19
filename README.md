# CohortLint

CohortLint checks metadata tables immediately before multi-cohort omics integration. It
reports structural, unit, vocabulary, completeness, study-design, and privacy problems
without reading expression matrices or attempting batch correction.

The project is being implemented milestone-by-milestone from `SPEC.md`.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
cohortlint --help
```
