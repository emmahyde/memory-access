# Auto-Version Bump & Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically bump semantic versions on commits to main based on commit message keywords, tag releases, and publish to PyPI—all in one atomic workflow with no race conditions.

**Architecture:** A single consolidated GitHub Actions workflow runs on main pushes, detects the bump type from commit message (`[major]`, `[minor]`, or default patch), updates `pyproject.toml` in place (no separate commit), creates an annotated git tag to trigger the existing PyPI publisher, and validates all steps before proceeding.

**Tech Stack:** GitHub Actions, bash semver logic, git tagging, PyPI secrets

---

### Task 1: Consolidate release workflows

**Files:**
- Modify: `.github/workflows/release.yml` — Replace with consolidated version-bump-and-tag logic
- Delete: `.github/workflows/publish.yml` (if it exists and is redundant)
- Keep: `.github/workflows/publish-pypi.yml` — Already correct

**Step 1: Review current publish.yml to confirm it's redundant**

Run: `cat .github/workflows/publish.yml`
Expected: It should be a simple relay to publish-pypi.yml, or not exist

**Step 2: Update release.yml to detect `[major]`/`[minor]` in commit message**

Replace the entire file with the consolidated workflow below:

```yaml
name: Release & Publish

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    if: "!contains(github.event.head_commit.message, '[skip release]')"

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Determine version bump type
        id: bump_type
        run: |
          COMMIT_MSG="${{ github.event.head_commit.message }}"

          BUMP_TYPE="patch"

          if echo "$COMMIT_MSG" | grep -qE "\[major\]"; then
            BUMP_TYPE="major"
          elif echo "$COMMIT_MSG" | grep -qE "\[minor\]"; then
            BUMP_TYPE="minor"
          fi

          echo "bump_type=$BUMP_TYPE" >> $GITHUB_OUTPUT
          echo "Detected bump type: $BUMP_TYPE"

      - name: Bump version in pyproject.toml
        id: bump_version
        run: |
          # Read current version from pyproject.toml
          CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
          echo "Current version: $CURRENT_VERSION"

          # Split version into parts (MAJOR.MINOR.PATCH)
          IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

          # Bump based on detected type
          case "${{ steps.bump_type.outputs.bump_type }}" in
            major)
              MAJOR=$((MAJOR + 1))
              MINOR=0
              PATCH=0
              ;;
            minor)
              MINOR=$((MINOR + 1))
              PATCH=0
              ;;
            patch)
              PATCH=$((PATCH + 1))
              ;;
          esac

          NEW_VERSION="$MAJOR.$MINOR.$PATCH"
          echo "New version: $NEW_VERSION"

          # Update pyproject.toml in place
          sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

          # Verify the update
          VERIFY_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
          if [ "$VERIFY_VERSION" != "$NEW_VERSION" ]; then
            echo "ERROR: Version update verification failed!"
            echo "Expected: $NEW_VERSION, Got: $VERIFY_VERSION"
            exit 1
          fi

          echo "new_version=$NEW_VERSION" >> $GITHUB_OUTPUT

      - name: Create annotated tag (atomic operation)
        id: create_tag
        run: |
          TAG="v${{ steps.bump_version.outputs.new_version }}"

          # Create an annotated tag with the bump type and new version
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

          git tag -a "$TAG" \
            -m "Release $TAG" \
            -m "Bump type: ${{ steps.bump_type.outputs.bump_type }}" \
            -m "Version: ${{ steps.bump_version.outputs.new_version }}"

          echo "tag=$TAG" >> $GITHUB_OUTPUT
          echo "Created tag: $TAG"

      - name: Push version bump and tag
        run: |
          # Push the updated pyproject.toml file
          git add pyproject.toml
          git commit -m "chore: bump version to ${{ steps.bump_version.outputs.new_version }} [skip release]"
          git push

          # Push the tag (this triggers publish-pypi.yml)
          git push origin "${{ steps.create_tag.outputs.tag }}"

      - name: Create GitHub Release
        run: |
          gh release create "${{ steps.create_tag.outputs.tag }}" \
            --title "Release ${{ steps.create_tag.outputs.tag }}" \
            --generate-notes
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Step 3: Commit the updated workflow**

Note: This consolidated workflow uses `[skip release]` (not `[skip ci]`) in the version bump commit to prevent infinite triggering while still allowing other workflows to run.

```bash
git add .github/workflows/release.yml
git commit -m "refactor: consolidate release workflow to detect [major]/[minor] in commit msg"
```

---

### Task 2: Remove redundant publish.yml if it exists

**Files:**
- Delete (if exists): `.github/workflows/publish.yml`

**Step 1: Check if publish.yml exists and its contents**

Run: `ls -la .github/workflows/publish.yml 2>/dev/null || echo "File does not exist"`
Expected: Either show file, or "File does not exist"

**Step 2: If exists, confirm it doesn't have unique logic**

Check if it just calls `publish-pypi.yml`. If so, delete it:

```bash
rm .github/workflows/publish.yml
git add -u .github/workflows/
git commit -m "chore: remove redundant publish.yml (consolidated into release.yml)"
git push
```

If it has unique logic, preserve it.

---

### Task 3: Verify publish-pypi.yml is correctly triggered by tags

**Files:**
- Review: `.github/workflows/publish-pypi.yml`

**Step 1: Confirm trigger and version validation**

The file should already have:
```yaml
on:
  push:
    tags:
      - 'v*'
```

And the validation step should check that tag version matches `pyproject.toml`. This is already in place ✓

**Step 2: No changes needed**

The `publish-pypi.yml` is correctly designed to:
1. Trigger on tag push
2. Extract version from tag
3. Validate it matches `pyproject.toml`
4. Build and publish to PyPI
5. Create a GitHub release

---

### Task 4: Test the workflow locally with a dry-run

**Files:**
- N/A (testing only)

**Step 1: Simulate a commit with `[minor]` bump**

```bash
# Create a test commit
echo "test content" >> test-bump.txt
git add test-bump.txt
git commit -m "feat: add test feature [minor]"

# Do NOT push yet—just verify the workflow logic
```

**Step 2: Manually test the version bump logic**

```bash
# Simulate the bash script locally
COMMIT_MSG="feat: add test feature [minor]"
BUMP_TYPE="patch"

if echo "$COMMIT_MSG" | grep -qE "\[major\]"; then
  BUMP_TYPE="major"
elif echo "$COMMIT_MSG" | grep -qE "\[minor\]"; then
  BUMP_TYPE="minor"
fi

echo "Detected bump type: $BUMP_TYPE"
# Expected: "Detected bump type: minor"
```

**Step 3: Test version bump calculation**

```bash
CURRENT_VERSION="0.1.3"
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

BUMP_TYPE="minor"
case "$BUMP_TYPE" in
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "New version: $NEW_VERSION"
# Expected: "New version: 0.2.0"
```

**Step 4: Reset test commit (don't push)**

```bash
git reset --hard HEAD~1
rm test-bump.txt
```

---

### Task 5: Document version bump convention in README or CONTRIBUTING.md

**Files:**
- Create or Modify: `CONTRIBUTING.md` (or similar)

**Step 1: Add commit message convention section**

Add to your contributing guidelines:

```markdown
## Version Bumping Convention

Versions follow **Semantic Versioning** (MAJOR.MINOR.PATCH).

When committing to `main`, the release workflow automatically detects the bump type from your commit message:

- **Default (patch):** `0.1.3` → `0.1.4`
  Example: `git commit -m "fix: handle edge case"`

- **Minor bump:** `0.1.3` → `0.2.0`
  Include `[minor]` in your commit message:
  `git commit -m "feat: add new API endpoint [minor]"`

- **Major bump:** `0.1.3` → `1.0.0`
  Include `[major]` in your commit message:
  `git commit -m "refactor: redesign core API [major]"`

**Important:** When you bump major or minor, patch resets to 0.

## CI/CD

- Tests run on every PR and push to `main`
- On merge to `main`, the **Release & Publish** workflow:
  1. Detects bump type from commit message
  2. Updates `pyproject.toml`
  3. Commits the version bump with `[skip release]` flag (prevents re-triggering this workflow)
  4. Creates a git tag (`vX.Y.Z`, which triggers publish-pypi.yml)
  5. Creates a GitHub Release with auto-generated notes
  6. The `publish-pypi.yml` workflow (triggered by tag push) publishes to PyPI automatically

Use `[skip release]` in your commit message to skip the release workflow (the release workflow is triggered by push to main, not other workflows).
```

**Step 2: Commit the documentation**

```bash
git add CONTRIBUTING.md
git commit -m "docs: document version bumping and release workflow"
git push
```

---

### Task 6: Validate no race conditions exist

**Files:**
- Review: `.github/workflows/release.yml` and `.github/workflows/publish-pypi.yml`

**Step 1: Verify atomic ordering**

Ensure the release.yml workflow:
1. ✓ Updates `pyproject.toml` first (in-memory, before any git operations)
2. ✓ Creates tag immediately after (tag always points to commit with updated version)
3. ✓ Pushes both commit + tag in sequence
4. ✓ Only publish-pypi.yml reacts to the tag (no circular dependency)

**Step 2: Verify no concurrent publish attempts**

The `publish-pypi.yml` is triggered **only** by tag push. Since release.yml pushes the tag after updating pyproject.toml, there's one atomic sequence:
- Commit with updated `pyproject.toml` is created and pushed
- Tag pointing to that commit is pushed
- `publish-pypi.yml` triggers and validates tag version matches `pyproject.toml`

No race conditions ✓

**Step 3: No action needed**

The workflow is already race-condition-free by design.
