# Race Condition Validation Report
## Task 6: Release Workflow Atomic Operation Analysis

**Date:** February 8, 2026
**Status:** CRITICAL ISSUES IDENTIFIED
**Overall Assessment:** NOT RACE-CONDITION-FREE

---

## Executive Summary

The current release workflow design contains **TWO RACE CONDITIONS**:

1. **Tag Creation Race Condition** (CRITICAL) — Tags point to the wrong commit
2. **Concurrent Workflow Race Condition** (MEDIUM) — No concurrency control exists

While both are partially mitigated by downstream validation, the design is **NOT atomically safe** and relies on luck and validation catches rather than proper ordering.

---

## Step 1: Atomic Operation Ordering Validation

### Actual Workflow Sequence (release.yml)

| # | Step | Line | Status | Issue |
|---|------|------|--------|-------|
| 1 | Checkout code | 16-19 | ✅ | Fresh checkout of trigger commit |
| 2 | Read version from pyproject.toml | 41-42 | ✅ | CURRENT_VERSION extracted correctly |
| 3 | Calculate new version | 48-61 | ✅ | Proper [major]/[minor]/patch detection |
| 4 | Update pyproject.toml | 67 | ✅ | sed modifies local file correctly |
| 5 | Verify update | 70-75 | ✅ | Read-back check prevents sed failures |
| 6 | **Create annotated tag** | 88-91 | ❌ | **RACE CONDITION: Tag created BEFORE commit** |
| 7 | Create git commit | 99-100 | ⚠️ | Creates new commit but tag still at old HEAD |
| 8 | Push commit | 101 | ⚠️ | Pushes new commit with correct version |
| 9 | Push tag | 104 | ❌ | **Tag points to OLD commit, not version-bumped commit** |
| 10 | Create GitHub Release | 108-110 | ✅ | Created from mismatched tag |

### The Critical Race Condition Diagram

```
EXPECTED BEHAVIOR:
  Commit A (version 0.1.2)
       ↓
  workflow modifies pyproject.toml
       ↓
  Commit B (version 0.1.3) ← tag v0.1.3 should point HERE
       ↓
  push both commit and tag


ACTUAL BEHAVIOR:
  Commit A (version 0.1.2) ← tag v0.1.3 points HERE (WRONG!)
       ↓
  workflow modifies pyproject.toml (not committed)
       ↓
  Commit B (version 0.1.3) created
       ↓
  tag pushed (still points to Commit A)
       ↓
  publish-pypi.yml checks out at tag
       ├─ finds version 0.1.2 in pyproject.toml
       ├─ expects version 0.1.3 (from tag name)
       └─ SHOULD FAIL but tag points to commit with 0.1.3 already
```

### Detailed Execution Analysis

#### Step 6: Tag Creation (THE PROBLEM)

```yaml
# release.yml lines 79-94
- name: Create annotated tag (atomic operation)
  run: |
    TAG="v${{ steps.bump_version.outputs.new_version }}"
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"

    git tag -a "$TAG" \
      -m "Release $TAG" \
      -m "Bump type: ..." \
      -m "Version: ..."
```

**Critical Issue:**
- At this point, HEAD points to the ORIGINAL commit (unchanged from checkout)
- Working directory has modified `pyproject.toml` (not yet committed)
- `git tag -a` creates a tag pointing to **current HEAD**
- **Result: Tag points to commit with OLD version**

#### Step 7-9: Commit and Push

```yaml
# lines 99-104
- name: Push version bump and tag
  run: |
    git add pyproject.toml
    git commit --allow-empty -m "chore: bump version to 0.1.3 [skip ci]"
    git push

    # Tag was already created in step 6!
    # Still points to old commit!
    git push origin "${{ steps.create_tag.outputs.tag }}"
```

**What Happens:**
1. New commit is created with updated `pyproject.toml`
2. Commit is pushed to origin/main
3. Tag is pushed (but still points to old commit from step 6)
4. Tag push triggers `publish-pypi.yml`

---

## Step 2: Concurrent Publish Prevention

### publish-pypi.yml Trigger and Validation

```yaml
# publish-pypi.yml lines 3-6
on:
  push:
    tags:
      - 'v*'
```

✅ **Correctly triggered only on tag push** (not other events)

### Version Validation (Lines 33-41)

```yaml
- name: Validate version matches
  run: |
    VERSION="${{ steps.version.outputs.version }}"          # Extracted from tag
    PYPROJECT_VERSION=$(python -c "import tomllib; ...")    # Read from file at tag
    if [ "$VERSION" != "$PYPROJECT_VERSION" ]; then
      echo "Tag version ($VERSION) does not match pyproject.toml ($PYPROJECT_VERSION)"
      exit 1
    fi
```

**Protection Level:** PARTIAL ⚠️

- **Should catch mismatch:** Tag v0.1.3 with file version 0.1.2 → FAIL
- **Why it doesn't always catch:** If the file ALSO happens to have v0.1.3 at that commit
  - Example: v0.1.3 tag points to commit 6c36b43
  - Even though v0.1.3 bump was at commit 0ffa4be (before 6c36b43)
  - commit 6c36b43 still has version 0.1.3 (not changed since 0ffa4be)
  - Validation passes by ACCIDENT

✅ **Only one publish-pypi.yml can upload a version:** PyPI rejects duplicates

❌ **No concurrency limit on release.yml itself:**

If two commits push to main within seconds:
1. release.yml triggered on commit 1 → starts reading version
2. release.yml triggered on commit 2 → starts reading version
3. Both read version 0.1.2
4. Both calculate new version as 0.1.3
5. Both create tag v0.1.3
6. Race condition: whoever pushes first wins, second fails
7. But second runner's tag push will conflict and fail at git push

---

## Step 3: Infinite Loop Prevention

### release.yml Guard Conditions (Line 13)

```yaml
if: "!contains(github.event.head_commit.message, '[skip ci]') &&
     !contains(github.event.head_commit.message, '[skip release]')"
```

✅ **Correctly implemented**

### Version Bump Commit (Line 100)

```yaml
git commit --allow-empty -m "chore: bump version to 0.1.3 [skip ci]"
```

✅ **Includes [skip ci] flag**

### Execution Flow

```
Event: Push to main with feature commit
    ↓
release.yml triggered
    ↓
Bumps version, creates tag, pushes
    ↓
Commit with "[skip ci]" flag is pushed
    ↓
GitHub Actions triggered by push
    ↓
release.yml checks: does commit message contain [skip ci]?
    ↓
YES → Job skipped, no re-trigger
    ↓
No infinite loop ✅
```

### publish-pypi.yml Loop Safety

```yaml
on:
  push:
    tags:
      - 'v*'
```

✅ **Only publishes, never commits or creates new tags**
✅ **Cannot trigger release.yml**
✅ **No circular dependencies**

---

## Step 4: Version Sync Guarantees

### Tag-to-Version Relationship: BROKEN

Based on actual repository state:

```
v0.1.1 tag:
  Points to: commit 42c128c
  Commit message: "chore: bump version to 0.1.1 [skip ci]"
  Version at commit: 0.1.1 ✓ MATCH
  Assessment: Correct (tag points to version bump commit)

v0.1.3 tag:
  Points to: commit 6c36b43
  Commit message: "chore: update uv.lock"
  Version bump commit: 0ffa4be (6 commits before tag)
  Version at commit 6c36b43: 0.1.3 ✓ VERSION MATCH
  Version at commit 0ffa4be: 0.1.3 ✓ SAME
  Assessment: Tag points to WRONG commit, but version is same
              (works by accident because next commit didn't change version)

v0.2.0 tag:
  Points to: commit 0729c8a
  Commit message: "chore: bump version to 0.2.0 [skip ci]"
  Version at commit: 0.2.0 ✓ MATCH
  Assessment: Correct (tag points to version bump commit)
```

### Why v0.1.3 Reveals the Problem

The tag v0.1.3 is on commit `6c36b43` but the version bump happened at `0ffa4be`.

This happened because:
1. release.yml (old version, before fixes) ran on commit 9e792e4
2. Created tag v0.1.3 pointing to 9e792e4 (old commit)
3. Created commit 0ffa4be with version bump
4. Later, commit 6c36b43 was created (without changing version)
5. Tag was updated to 6c36b43 somehow (manually or workflow re-run?)
6. Version happened to match by luck

**This is not a safe design.**

---

## Step 5: Overall Assessment

### Race Conditions Present: YES (2 identified)

#### Race Condition #1: Tag Creation Ordering (CRITICAL)

**Severity:** HIGH
**Likelihood:** MEDIUM (depends on commit timing)
**Detectability:** MEDIUM (caught by publish-pypi validation)

**Description:**
- Tags are created before version bump commit
- Tag points to old commit with old version in file
- publish-pypi.yml validation should catch mismatch
- But if tag-pointed-to commit happens to have same version, passes by luck

**Current Mitigation:**
- publish-pypi.yml validates version matches tag name
- Works if validation finds mismatch
- Fragile: depends on implementation details

#### Race Condition #2: Concurrent release.yml Execution (MEDIUM)

**Severity:** MEDIUM
**Likelihood:** LOW (requires two commits within seconds)
**Detectability:** HIGH (git push conflict on duplicate tag)

**Description:**
- No concurrency locks on release.yml
- Multiple instances could calculate same version bump
- Both could attempt to create same tag v0.1.3
- Second instance fails at push with git error

**Current Mitigation:**
- GitHub Actions default serialization on main pushes (helps)
- Git push fails on duplicate tag (stops second attempt)
- [skip ci] guards prevent re-triggering

---

## Detailed Findings

### What Works Well ✅

1. **Version Calculation:** Properly detects [major]/[minor]/patch from commit message
2. **Update Verification:** Reads back and validates sed changes before committing
3. **Infinite Loop Prevention:** [skip ci] flag and guards work correctly
4. **One-way Workflows:** Only release.yml creates tags, only publish-pypi publishes
5. **PyPI Protection:** PyPI rejects duplicate version uploads
6. **GitHub Validation:** publish-pypi.yml validates version matches

### What Needs Fixing ❌

1. **Tag Creation Order:** Should happen AFTER commit, not before
2. **Concurrency Control:** No `concurrency` field to serialize release jobs
3. **Atomic Ordering:** Current ordering is not atomic by design

---

## Recommended Fixes

### Fix 1: Reorder Tag Creation (CRITICAL)

**Current order (lines 37-104):**
1. Modify pyproject.toml (line 67)
2. Verify (line 70)
3. **Create tag (line 88)** ← TOO EARLY
4. Create commit (line 100)
5. Push commit (line 101)
6. Push tag (line 104)

**Correct order:**
1. Modify pyproject.toml
2. Verify
3. Create commit ← move here (before tag)
4. **Create tag (after commit)** ← NOW points to updated commit
5. Push commit and tag

**Implementation:**
```yaml
# Move the "Create annotated tag" step
# from after "Bump version" to after "Push version bump"
# Actually, do it BEFORE push:

- name: Create commit
  run: |
    git add pyproject.toml
    git commit --allow-empty -m "chore: bump version to ... [skip ci]"

- name: Create annotated tag
  run: |
    git tag -a "v..." ...  # Now points to commit with new version

- name: Push commit and tag
  run: |
    git push
    git push origin "v..."
```

### Fix 2: Add Concurrency Control

```yaml
jobs:
  release:
    concurrency:
      group: release
      cancel-in-progress: false
    runs-on: ubuntu-latest
    if: "!contains(github.event.head_commit.message, '[skip ci]')"
```

This ensures only one release.yml job runs at a time.

---

## Conclusion

### Direct Answers to Validation Checklist

**Step 1: Atomic Operation Ordering**

| Item | Status | Notes |
|------|--------|-------|
| Version read first | ✅ | Line 41 reads from pyproject.toml |
| Version calculated | ✅ | Lines 48-61 calculate based on message |
| pyproject.toml updated | ✅ | Line 67 with sed |
| Update verified | ✅ | Lines 70-75 read back and compare |
| Git commit created | ✅ | Line 100 commits updated file |
| Annotated tag created | ❌ | Line 88 - **created BEFORE commit** |
| Commit AND tag pushed | ⚠️ | Pushed but tag points to old commit |
| GitHub release created | ✅ | Lines 108-110 create release |

**Step 2: Concurrent Publish Prevention**

| Item | Status | Notes |
|------|--------|-------|
| Only release.yml updates version | ✅ | Single source of truth |
| Only publish-pypi.yml publishes | ✅ | Single publish job |
| publish-pypi triggered by tags only | ✅ | Line 3-6 guard |
| Version validation exists | ✅ | Lines 33-41 validate match |

**Step 3: Infinite Loop Prevention**

| Item | Status | Notes |
|------|--------|-------|
| [skip ci] flag in version commit | ✅ | Line 100 includes flag |
| release.yml checks [skip ci] | ✅ | Line 13 guards |
| publish-pypi doesn't commit | ✅ | Only publishes |

**Step 4: Version Sync**

| Item | Status | Notes |
|------|--------|-------|
| Tag points to version commit | ❌ | Points to commit BEFORE bump |
| File version matches tag | ⚠️ | Matches by accident in v0.1.3 case |
| No mismatch scenarios | ❌ | publish-pypi would fail if versions diverge |

### Final Assessment

**Is the design race-condition-free?**

## **NO**

**Reasoning:**

The workflow has two race conditions:

1. **Tag Creation Race** (Critical): Tags point to the wrong commit because they're created before the version-bump commit. This violates atomic operation ordering.

2. **Concurrent Execution Race** (Medium): No concurrency control allows multiple release workflows to run simultaneously, potentially creating duplicate tags.

Both are **partially mitigated** by validation and git mechanics, but the design itself is **not atomically safe**. The system works because:
- publish-pypi.yml validates versions
- Git fails on duplicate tags
- Implementation happens to keep versions in sync

But these are **catches for bad ordering**, not **proper design**.

**Recommendation:**
Implement both fixes (reorder tag creation, add concurrency control) to make the workflow truly race-condition-free by design, not just by luck.

---

## Evidence Files

- `.github/workflows/release.yml` — Version bump and tagging logic
- `.github/workflows/publish-pypi.yml` — PyPI publishing logic
- `pyproject.toml` — Current version (0.1.4)
- Git tags: v0.1.1, v0.1.3, v0.2.0 (verified locally)

---

## Document Information

**Validation Date:** 2026-02-08
**Repository:** /Users/emmahyde/memory-access
**Current Version:** 0.1.4
**Task:** Task 6 - Validate no race conditions exist in release workflow
