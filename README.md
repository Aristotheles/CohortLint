# CohortLint

CohortLint checks cohort metadata immediately before multi-cohort omics integration. It
finds unit mismatches, inconsistent vocabularies, missing covariates, non-estimable study
designs, and privacy-hygiene risks without reading expression matrices or attempting batch
correction.

## Installation

```bash
pip install cohortlint
```

Optional formats and ontology mapping:

```bash
pip install "cohortlint[ontology]"
pip install "cohortlint[anndata]"
```

## Worked example

Create a starter configuration:

```bash
cohortlint init --output cohortlint.yaml
```

Declare the biological effect and technical batch variables:

```yaml
version: 1
cohorts:
  - name: berlin
    path: data/berlin.csv
    sample_id: patient_id
  - name: hannover
    path: data/hannover.tsv
    sample_id: sample_id
schema:
  age:
    type: numeric
    unit: years
    range: [0, 120]
    required: true
  condition:
    type: categorical
    role: biological
    required: true
  batch:
    type: categorical
    role: technical
    required: true
privacy:
  k_anonymity_threshold: 5
output:
  lang: en
```

Run diagnostics and produce an escaped standalone HTML report:

```bash
cohortlint check --config cohortlint.yaml --format html --output report.html
```

Apply only safe metadata rewrites and record provenance:

```bash
cohortlint harmonize --config cohortlint.yaml \
  --output merged.csv --mappings mappings.sssom.tsv
```

`harmonize` never rewrites design findings. Complete batch-condition confounding cannot be
repaired computationally.

## Exit codes

- `0`: clean or below the configured fail threshold
- `1`: findings at or above `--fail-on`
- `2`: invalid configuration, unreadable input, or unsafe output target

## Security and privacy

Privacy findings are heuristics and are not compliance assessments. P001 reports counts,
never matching identifier values. HTML output uses autoescaping and a restrictive Content
Security Policy. See [SECURITY.md](SECURITY.md) for the threat model and reporting process.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy
pytest --cov=cohortlint
bandit -r src
pip-audit
```

The rule catalogue is generated in [docs/rules.md](docs/rules.md), and dependency licences
are recorded in [docs/dependencies.md](docs/dependencies.md).
