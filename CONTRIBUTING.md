# Contributing

Thanks for contributing to Agent Performance Review.

## Development flow

1. Make changes in a feature branch.
2. Run local checks:

```bash
./tests/run.sh
```

3. If card rendering changed, regenerate the sample card and verify it is readable at half size.
4. Before tagging a release, run:

```bash
./scripts/release-preflight.sh
```

## Quality expectations

- Keep all production metrics grounded in real parsed data.
- Do not add telemetry or remote data exfiltration.
- Keep recommendation text actionable (explicit key/value or concrete action).
- Preserve output schema of `scripts/analyze.sh` for backward compatibility.

## Template contributions

When adding roasts or recommendations:

- Roast templates must reference at least 2 real placeholders.
- Add only placeholders that are derivable from analysis output.
- Recommendation patterns should include a clear condition and measurable impact.

## Pull requests

- Use the PR checklist in `.github/pull_request_template.md`.
- Include exact validation commands and outputs.
- Keep changes scoped; separate refactors from behavior changes when possible.

## Issues

- Use the issue templates under `.github/ISSUE_TEMPLATE/`.
- Security reports should go through `SECURITY.md`, not public issues.
