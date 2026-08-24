# Releasing

How to cut a Nyctea release, and how the automation behind it works.

## The actual flow

Release publishing runs on trusted publishing (OIDC) since PR #18 and #22.
There is no `PYPI_API_TOKEN`, and there should not be one.
A tag push does not publish anything by itself; a human always reviews a draft first.

1. Bump `version` in `pyproject.toml`.
2. Commit and merge to `main` via PR, the same as any other change.
3. Tag the merge commit and push the tag:
   ```bash
   git tag vx.y.z && git push origin vx.y.z
   ```
4. **`Draft Release`** (`release-notes.yaml`) fires on the tag push and creates a draft GitHub Release with generated notes, grouped by PR label according to `.github/release.yml`. Nothing is published yet.
5. Review the draft. This is the point to edit the notes if the auto-generated summary needs a human pass, not a step to skip. Click **Publish**.
6. Publishing the release fires **`Publish to PyPI`** (`pypi-publish.yaml`). It builds the package and uploads it to PyPI through trusted publishing, with no token and no manual `uv publish`.

There is no maintained `CHANGELOG.md`. The GitHub Release for each tag is the changelog, the same
way Polars does it. Label PRs correctly (`bug`, `enhancement`, `documentation`, `breaking`) so
`.github/release.yml` sorts them into the right section automatically.

## `scripts/release.sh` is superseded, do not use it

It predates trusted publishing and calls `uv publish dist/*` directly with a token, which bypasses the draft-review step entirely.
It's kept for now; delete it once nobody reaches for it out of habit.

## Versioning

Semantic Versioning applies, pre-1.0:

| Change | Bump |
| --- | --- |
| Breaking change or major new feature | `0.x.0` to `0.(x+1).0` |
| Bug fix, minor improvement | `0.x.y` to `0.x.(y+1)` |

At 1.0.0, standard semver applies: major for breaking changes, minor for backward-compatible features, patch for fixes.

Docs-only changes, CI or workflow changes, test-only changes, and ADRs do not bump the version.
Anything under `src/nyctea/` that affects behavior, and any dependency update that changes runtime behavior, does.

Breaking changes always get an entry in [breaking changes](../releases/breaking-changes.md). That
page is maintained by hand, unlike the release notes; a one-line changelog entry is not enough
context for a migration.

## Prerequisites, one-time

- A PyPI trusted publisher registered at pypi.org for this repo, workflow `pypi-publish.yaml`, environment `release`. See PyPI's [trusted publishing docs](https://docs.pypi.org/trusted-publishers/) if this ever needs re-registering; a repo rename or workflow rename invalidates it.
- The `Development Status` classifier in `pyproject.toml` should track reality: `3 - Alpha` now, `4 - Beta` once the API stabilizes, `5 - Production/Stable` at 1.0.0.

## Troubleshooting

**"Package already exists" on PyPI.**
Versions cannot be replaced once published. Bump and retry.

**Draft release never appeared.**
Confirm the tag matches `v*` and was pushed to the actual remote, not just created locally: `git push origin <tag>`.
