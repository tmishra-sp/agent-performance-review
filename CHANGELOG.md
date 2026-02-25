# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- `scripts/pilot-scorecard.py` to compare baseline vs current analysis snapshots and produce leader-friendly impact scorecards (Markdown/JSON).
- Test fixtures and CI coverage for scorecard generation.

## [1.0.1] - 2026-02-24

### Added
- Dedicated `Security` workflow (`.github/workflows/security.yml`) running `pip-audit` and `bandit`.
- Dependabot configuration for `pip` and GitHub Actions updates (`.github/dependabot.yml`).
- Central dependency manifest (`requirements.txt`).

### Changed
- Pinned GitHub Actions to immutable commit SHAs in CI and triage workflows.
- Updated issue-triage advisory link to current repository owner.
- Enforced Python `>=3.10` in dependency installer and switched installer to `python3 -m pip`.
- Updated Pillow constraint to `>=12.1.1,<13.0.0`.

### Security
- Enabled GitHub vulnerability alerts and required `security` status checks on `main`.
- Preserved strict branch protections (PR required, review required, no force-push/delete).

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
