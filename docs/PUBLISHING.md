# Publishing Guide

This document explains how to publish memory-access to PyPI.

## Prerequisites

1. **PyPI Account** - Create one at https://pypi.org/account/register/
2. **GitHub Secret** - Add your PyPI token as `PYPI_API_TOKEN` in GitHub repo settings

## One-Time Setup

### 1. Create PyPI Account

Go to https://pypi.org/account/register/ and sign up.

### 2. Create API Token

1. Log into PyPI
2. Click your avatar → Account Settings
3. Scroll to "API tokens"
4. Click "Add API token"
5. Set scope to "Entire repository"
6. Copy the token (starts with `pypi-`)

### 3. Add to GitHub Secrets

1. Go to https://github.com/emmahyde/memory-access/settings/secrets/actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: (paste the token from step 2)
5. Click "Add secret"

## Publishing a Release

### Version Format

Versions follow [Semantic Versioning](https://semver.org/):
- `v0.1.2` - patch release (bug fixes)
- `v0.2.0` - minor release (new features, backwards compatible)
- `v1.0.0` - major release (breaking changes)

### Release Steps

1. **Update Version** in `pyproject.toml`:
   ```toml
   [project]
   version = "0.2.0"
   ```

2. **Update CHANGELOG.md**:
   ```markdown
   ## [0.2.0] - 2025-02-XX

   ### Added
   - New feature description

   ### Changed
   - Change description

   ### Fixed
   - Bug fix description
   ```

3. **Commit Changes**:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "Release v0.2.0"
   ```

4. **Create Git Tag**:
   ```bash
   git tag v0.2.0
   git push origin main --tags
   ```

5. **Watch the Magic** ✨

   The GitHub Actions workflow will:
   - Validate the version matches
   - Build the package
   - Publish to PyPI
   - Create a GitHub Release
   - Generate release notes

## Verification

After publishing:

1. **Check PyPI**: https://pypi.org/project/memory-access/
2. **Test Installation**:
   ```bash
   pip install memory-access
   ```
3. **Check Release**: https://github.com/emmahyde/memory-access/releases

## Troubleshooting

### Version Mismatch Error

The tag version must match `pyproject.toml`. For tag `v0.2.0`, the version in `pyproject.toml` must be `0.2.0` (without the `v`).

### Token Not Found

Make sure `PYPI_API_TOKEN` is set in GitHub secrets. Check:
1. Repo Settings → Secrets and variables → Actions
2. Token starts with `pypi-`
3. Token hasn't expired

### Build Fails

Run locally first:
```bash
uv sync --group dev
uv run pytest
python -m build
```

## Pre-Release Versions

For alpha/beta/RC releases, use tags like:
- `v0.2.0-alpha.1`
- `v0.2.0-beta.1`
- `v0.2.0-rc.1`

These will automatically be marked as pre-releases on PyPI and GitHub.

## References

- [PyPI Help](https://pypi.org/help/)
- [Python Packaging Guide](https://packaging.python.org/)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
