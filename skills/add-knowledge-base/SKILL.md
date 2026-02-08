---
name: add-knowledge-base
description: Interactively create and ingest a knowledge base from crawled URLs, single pages, or Firecrawl JSON folders with real-time progress and detailed statistics
---

# Add Knowledge Base

This skill guides you through creating a knowledge base step-by-step, with validation, real-time progress, and detailed statistics.

## Overview

Create a new knowledge base (KB) by choosing a data source, providing parameters, and automatically ingesting content with real-time progress tracking.

Three ingestion modes are supported:
- **Crawl**: Index an entire website (recursive crawl from a URL)
- **Scrape**: Index a single page
- **From-Dir**: Load pre-crawled Firecrawl JSON files from a directory

## Interactive Flow

The skill will guide you through:

1. **Choose Source Type** — Select crawl, scrape, or from-dir
2. **Validate & Collect Parameters** — KB name (slug), optional description, source-specific settings
3. **Show Confirmation** — Review all settings before proceeding
4. **Execute & Stream Progress** — Real-time progress display during ingestion
5. **Display Summary** — Frame distribution, confidence stats, ingestion time

## Parameter Validation

### KB Name
- Must be lowercase alphanumeric + hyphens (no spaces, underscores, special chars)
- If KB already exists, you'll be asked: "Append chunks or replace?"
- Appending adds to the existing KB; replacing deletes old chunks and creates new

### URLs (crawl/scrape)
- Must start with `http://` or `https://`
- Basic format validation

### Directory (from-dir)
- Must exist and be readable
- Must contain at least one `.json` file (from Firecrawl)

### Page Limit (crawl only)
- Must be positive integer between 1–10,000
- Default: 1000

### Description (all modes)
- Optional
- Max 200 characters

## Error Handling & Recovery

If something fails during ingestion, the skill offers recovery options:

### Crawl timeout or network error
**Message**: "Crawl failed. Network issue or URL unreachable."
**Recovery options**:
- (A) Retry with lower page limit
- (B) Try a different URL
- (C) Cancel

If you retry, the same KB name is used (chunks append).

### Invalid directory or missing files
**Message**: "Directory not found or contains no .json files"
**Recovery options**:
- (A) Browse and select correct directory
- (B) Check directory contents with `ls`
- (C) Try different path
- (D) Cancel

### KB name conflict
**Message**: "KB '<name>' exists with X chunks. What would you like to do?"
**Recovery options**:
- (A) Append chunks to existing KB
- (B) Replace KB (delete old chunks, create fresh)
- (C) Use a different KB name

### Large ingestions hang
If no progress for 2+ minutes:
**Message**: "Still running. Cancel and retry with lower limit?"
**Recovery options**:
- (A) Continue waiting
- (B) Cancel and retry with smaller page limit

## Progress Display

During ingestion, you'll see real-time updates:
```
Creating KB "unity-docs"...
  [1/500] https://docs.unity.com/page1
  [2/500] https://docs.unity.com/page2
  ⏳ Ingesting... (2 min 15 sec elapsed)
```

## Final Summary

After successful ingestion:
```
✓ Created KB "unity-docs" with 287 chunks in 2m 45s
  Frame distribution: CAUSAL (35%), CONSTRAINT (22%), PATTERN (18%), PROCEDURE (15%), TAXONOMY (10%)
  Confidence: avg=0.91, min=0.60, max=1.00
```

If appending to an existing KB, you'll see before/after counts:
```
✓ Updated KB "unity-docs"
  Before: 150 chunks, After: 287 chunks (+137 new)
```

## Examples

### Example 1: Crawl a website
1. Choose: **Crawl**
2. KB Name: `unity-docs`
3. URL: `https://docs.unity.com/6000.0/Documentation/Manual/`
4. Page limit: `500`
5. Description: `Unity 6000 manual reference`
6. Confirm and watch progress
7. Results: 287 chunks ingested in 2m 45s

### Example 2: Load Firecrawl JSON files
1. Choose: **From-Dir**
2. KB Name: `my-project-docs`
3. Directory: `/Users/me/Downloads/firecrawl-export/`
4. Description: `Project documentation`
5. Confirm and watch progress
6. Results: 45 chunks ingested in 30 seconds

## Implementation Notes

For Claude Code:
- Use `AskUserQuestion` for interactive input (one question per turn)
- Use `Bash` to execute CLI commands: `uv run sem-mem kb new ...`
- Capture stderr for progress output
- Parse the knowledge_bases table to extract final stats
- Handle errors gracefully with recovery options

The skill leverages the `sem-mem kb` CLI tool family for execution.
