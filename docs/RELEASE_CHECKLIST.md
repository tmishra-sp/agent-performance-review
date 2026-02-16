# Release Checklist

Use this checklist for each tagged release.

## 1. Scope and versioning

- [ ] Confirm release scope (features/fixes/docs).
- [ ] Pick semantic version (`major.minor.patch`).
- [ ] Update `CHANGELOG.md` with release date and entries.

## 2. Quality gates

- [ ] Run consolidated release preflight:

```bash
./scripts/release-preflight.sh
```

- [ ] Run local tests:

```bash
./tests/run.sh
```

- [ ] Re-generate sample card deterministically:

```bash
python3 scripts/generate-card.py examples/sample-analysis.json examples/sample-card.png --fonts-dir card-template/fonts --seed 7
```

- [ ] Verify sample card dimensions and size target (<500KB).
- [ ] Validate JSON files:

```bash
jq empty references/roasts.json references/recommendations.json examples/sample-analysis.json
```

## 3. Product checks

- [ ] `SKILL.md` still matches actual scripts/paths/commands.
- [ ] No placeholder metrics in production behavior.
- [ ] Improvement plan recommendations remain actionable.
- [ ] Privacy promise still true (local processing, no telemetry).

## 4. Documentation checks

- [ ] README install flow still works as written.
- [ ] CONTRIBUTING and templates reflect current workflow.
- [ ] Asset license notes updated if assets/fonts changed.

## 5. GitHub release

- [ ] Create annotated tag (`vX.Y.Z`).
- [ ] Push tag.
- [ ] Draft GitHub Release notes from changelog.
- [ ] Include breaking changes and migration notes (if any).

## 6. Post-release

- [ ] Verify CI succeeded for tag.
- [ ] Smoke test install command in a fresh environment.
- [ ] Open follow-up issues for deferred items.
