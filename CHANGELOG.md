# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [1.0.0] - 2026-02-16

### Added
- Initial public release of Agent Performance Review skill.
- Session analyzer (`scripts/analyze.sh`) with task, cost, autonomous, skills, health, and rating output.
- PNG report renderer (`scripts/generate-card.py`) and sample assets.
- Roast/recommendation template datasets.
- CI workflow and fixture-based test harness.
- Issue templates, PR template, release checklist, and governance docs.

### Changed
- Hardened analyzer ingestion and metric correctness for malformed lines and autonomous usefulness accounting.
- Deterministic card generation support via `--seed`.

### Security
- Added `SECURITY.md` and private disclosure channel guidance.
