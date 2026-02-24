# Agent Performance Review v1.0.1

Security and release hardening update.

## Highlights

- Added a dedicated Security workflow to run dependency and static security scans on push/PR and weekly.
- Pinned GitHub Actions to immutable SHAs to reduce supply-chain drift risk.
- Introduced Dependabot automation for dependencies and workflow updates.
- Standardized dependencies in `requirements.txt` and updated Pillow to a non-vulnerable range.
- Strengthened installer behavior with explicit Python version enforcement (`>=3.10`).

## Security posture

- Branch protection on `main` requires:
  - pull request flow,
  - passing checks (`test`, `security`),
  - one approving review,
  - no force push,
  - no branch deletion.
- GitHub vulnerability alerts are enabled.

## Verification

- `./tests/run.sh`
- `python3.11 -m pip_audit -r requirements.txt`
- `python3.11 -m bandit -q -r scripts`

## Notes

- No production/pilot KPI claims are added in this release. Reported metrics in docs are strictly measured from local checks.
