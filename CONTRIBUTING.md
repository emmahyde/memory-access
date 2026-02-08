# Contributing to memory-access

Thank you for your interest in contributing to memory-access! This document provides guidelines for development, version management, and the release process.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/emmahyde/memory-access.git
   cd memory-access
   ```

2. Install dependencies:
   ```bash
   uv sync --group dev
   ```

3. Run tests to ensure everything works:
   ```bash
   uv run pytest
   ```

   For a specific test file:
   ```bash
   uv run pytest tests/test_storage.py
   ```

   For a specific test:
   ```bash
   uv run pytest tests/test_storage.py::TestInsightStoreInit::test_initialize_creates_tables
   ```

4. Run the MCP server locally:
   ```bash
   uv run memory-access
   ```

## Version Bumping Convention

This project follows **Semantic Versioning** (MAJOR.MINOR.PATCH).

### How Version Bumping Works

When code is merged to the `main` branch, the **Release & Publish** CI/CD workflow automatically:
1. Reads your commit message
2. Detects the version bump type from keywords
3. Updates `pyproject.toml` with the new version
4. Creates a git tag (`vX.Y.Z`)
5. Publishes to PyPI
6. Creates a GitHub Release with auto-generated notes

**You do not manually bump versions.** The CI/CD pipeline handles this automatically based on your commit message.

### Commit Message Keywords

Include one of these keywords in your commit message to specify the bump type:

#### Default (Patch Bump): `0.1.3` → `0.1.4`
No keyword needed. Patch bumps occur by default for any merge.

Example:
```bash
git commit -m "fix: handle edge case in normalizer"
```

#### Minor Bump: `0.1.3` → `0.2.0`
Include `[minor]` in your commit message.

Example:
```bash
git commit -m "feat: add new API endpoint for graph traversal [minor]"
```

#### Major Bump: `0.1.3` → `1.0.0`
Include `[major]` in your commit message.

Example:
```bash
git commit -m "refactor: redesign core API with breaking changes [major]"
```

**Important:** When bumping major or minor, the patch version resets to 0.

### Skipping the Release Workflow

To skip the automatic release and version bump entirely, use either:

```bash
# Skip all CI workflows
git commit -m "docs: update README [skip ci]"

# Skip only the release workflow
git commit -m "chore: update dependencies [skip release]"
```

## Submitting Changes

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and write tests if applicable.

3. **Run tests** to ensure nothing breaks:
   ```bash
   uv run pytest
   ```

4. **Commit with clear, descriptive messages** following the version bumping convention above:
   ```bash
   git commit -m "feat: describe what you added [minor]"
   ```

5. **Push to GitHub** and open a pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

## CI/CD Pipeline

### Triggers

- **Tests workflow (`tests.yml`)** — Runs on every push and PR to verify code quality
- **Release & Publish workflow (`release.yml`)** — Runs on merges to `main` (unless `[skip ci]` or `[skip release]` is in the commit message)
- **Publish to PyPI workflow (`publish-pypi.yml`)** — Triggered by git tags created by the release workflow

### What Happens on Merge to Main

1. The release workflow detects the bump type from your commit message
2. Version in `pyproject.toml` is automatically updated
3. A git tag is created (e.g., `v0.1.4`)
4. Changes are pushed back to `main`
5. The tag triggers the PyPI publish workflow
6. Your code is automatically published to PyPI
7. A GitHub Release is created with auto-generated notes

## Code Style

- Use clear, descriptive variable and function names
- Include docstrings for public APIs
- Follow PEP 8 conventions (enforced by tests where applicable)
- Write async-first code where applicable (this is an async-heavy codebase)

## Testing

- Write tests for new features and bug fixes
- Use the `tmp_db` fixture from `conftest.py` for isolated database tests
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work naturally
- Ensure all tests pass before opening a PR:
  ```bash
  uv run pytest
  ```

## Questions?

If you have questions or need clarification:
- Open an issue on GitHub
- Check existing documentation in README.md and CLAUDE.md
- Review the source code — it's well-commented and organized

## License

All contributions are licensed under the Apache-2.0 license. See the LICENSE file for details.
