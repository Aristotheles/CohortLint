# CohortLint build specification

CohortLint is a Python 3.11+ CLI and library for pre-integration diagnostics on
multi-cohort omics metadata. It reads metadata only and does not perform batch
correction, expression-matrix analysis, or ontology matching itself.

The implemented contract comprises:

- structural rules S001-S004;
- unit and encoding rules U001-U005;
- vocabulary rules V001-V003 through the optional `text2term` integration;
- completeness rules C001-C003;
- study-design rules D001-D006;
- privacy-hygiene rules P001-P003;
- English, German, and Turkish terminal, JSON, and HTML reporting;
- safe harmonization limited to U002, U003, and accepted V003 mappings;
- Python 3.11/3.12/3.13 support on Linux, macOS, and Windows.

Rule semantics and default severities are published in [docs/rules.md](docs/rules.md).
Configuration and CLI usage are documented in [README.md](README.md). The project is
MIT licensed, and every runtime dependency must use a permissive licence recorded in
[docs/dependencies.md](docs/dependencies.md).
