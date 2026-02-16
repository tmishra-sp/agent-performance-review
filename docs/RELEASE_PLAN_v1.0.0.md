# v1.0.0 Release Plan

Target: first public stable release for GitHub.

## Proposed release commit message

`chore(release): prepare v1.0.0`

## Tag

`v1.0.0`

## Changelog cut

Release section exists in `CHANGELOG.md`:
- `[1.0.0] - 2026-02-16`

## Release notes draft

See `docs/RELEASE_NOTES_v1.0.0.md`.

## Operator steps

1. Run preflight:

```bash
./scripts/release-preflight.sh
```

2. Commit release state:

```bash
git add .
git commit -m "chore(release): prepare v1.0.0"
```

3. Tag:

```bash
git tag -a v1.0.0 -m "v1.0.0"
```

4. Push branch + tag:

```bash
git push origin <branch>
git push origin v1.0.0
```

5. Create GitHub release using `docs/RELEASE_NOTES_v1.0.0.md`.
