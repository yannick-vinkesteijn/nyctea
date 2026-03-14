# Release Guide

This document describes how to release Nyctea to PyPI.

## Automated Release (Recommended)

Nyctea uses GitHub Actions to automatically publish to PyPI when you create a GitHub release.

### Prerequisites

1. PyPI account at [pypi.org](https://pypi.org)
2. PyPI API token added to GitHub secrets as `PYPI_API_TOKEN`
   - Create at [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/)
   - Add to [GitHub repo secrets](https://github.com/yannick-vinkesteijn/nyctea/settings/secrets/actions)

### Release Process

1. **Update version** in `pyproject.toml`:
   ```toml
   version = "0.2.0"
   ```

2. **Commit and push**:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin main
   ```

3. **Create GitHub release**:
   - Go to [Releases](https://github.com/yannick-vinkesteijn/nyctea/releases/new)
   - Click "Choose a tag" → Create new tag: `v0.2.0`
   - Set release title: `v0.2.0`
   - Add release notes
   - Click "Publish release"

4. **GitHub Actions will automatically**:
   - Build the package
   - Verify version matches tag
   - Publish to PyPI
   - Upload artifacts

5. **Verify**:
   - Check [Actions tab](https://github.com/yannick-vinkesteijn/nyctea/actions)
   - Verify on [PyPI](https://pypi.org/project/nyctea/)

## Manual Release (Alternative)

If you prefer manual control or want to test first:

## Quick Release with Script

The easiest way to release:

```bash
./scripts/release.sh 0.2.0
```

This script will:
1. Update version in `pyproject.toml`
2. Run tests
3. Build the package
4. Optionally publish to TestPyPI for testing
5. Publish to PyPI
6. Create git tag
7. Guide you through creating GitHub release

## Manual Release Process

If you prefer to do it manually:

### 1. Update Version

Edit `pyproject.toml`:
```toml
version = "0.2.0"
```

### 2. Run Tests

```bash
uv run pytest tests/ -v
```

### 3. Build Package

```bash
rm -rf dist/
uv build
```

### 4. Test on TestPyPI (Recommended)

```bash
# Publish to TestPyPI
uv publish --index https://test.pypi.org/legacy/ dist/*

# Test install
uv pip install --index-url https://test.pypi.org/simple/ nyctea==0.2.0
```

### 5. Publish to PyPI

```bash
uv publish dist/*
```

You'll be prompted for your API token.

Alternatively, set environment variable:
```bash
export UV_PUBLISH_TOKEN="pypi-YOUR-TOKEN-HERE"
uv publish dist/*
```

### 6. Tag Release

```bash
git add pyproject.toml
git commit -m "Bump version to 0.2.0"
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

### 7. Create GitHub Release

Go to [Releases](https://github.com/yannick-vinkesteijn/nyctea/releases/new) and create a new release from tag `v0.2.0`.

## Versioning

Nyctea follows [Semantic Versioning](https://semver.org/):

- **0.x.y** - Pre-1.0 releases (breaking changes allowed)
  - `0.1.0` → `0.2.0` - Breaking changes or major new features
  - `0.2.0` → `0.2.1` - Bug fixes, minor improvements
  - `0.2.1` → `0.3.0` - New features

- **1.0.0+** - Stable API
  - `1.0.0` → `2.0.0` - Breaking changes
  - `1.0.0` → `1.1.0` - New features (backward compatible)
  - `1.0.0` → `1.0.1` - Bug fixes

## Development Status

Current classifiers in `pyproject.toml`:
- `Development Status :: 3 - Alpha` - Early stage, API may change
- Change to `4 - Beta` when API stabilizes
- Change to `5 - Production/Stable` for 1.0.0+

## Troubleshooting

### "Invalid API token"

Make sure your token:
- Starts with `pypi-`
- Has appropriate scope (use "Entire account" initially)
- Is not expired

### "Package already exists"

You cannot replace a version once published. Increment version and try again.

### "Filename already exists"

Clean `dist/` folder before building:
```bash
rm -rf dist/
uv build
```
