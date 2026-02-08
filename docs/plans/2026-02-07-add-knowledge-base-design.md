# Add Knowledge Base Skill Design

## Overview

Interactive skill to guide users through creating knowledge bases from three sources: crawl (live URL), scrape (single page), or from-dir (Firecrawl JSON folder).

## User Flow

### Phase 1: Source Selection
User selects ingestion source type via multiple choice.

### Phase 2: Parameter Collection
Collect KB name (validated as slug), optional description, and source-specific parameters:
- **Crawl**: URL, page limit (default 1000)
- **Scrape**: URL
- **From-dir**: Directory path

### Phase 3: Execution & Feedback
Show summary, confirm, execute CLI, stream progress, show final stats.

## Parameter Validation

**KB Name**: Must be valid slug (lowercase alphanumeric + hyphens). Check if KB exists—if so, ask append or replace.

**URLs**: Must start with http/https.

**Directory**: Must exist and contain .json files.

**Limits**: Must be positive integer (1-10000).

## Progress & Stats

During ingestion, display real-time progress:
```
Creating KB "unity-docs"...
  [1/100] https://docs.unity.com/page1
  [2/100] https://docs.unity.com/page2
```

After completion, show summary:
```
✓ Created KB "unity-docs" with 287 chunks in 2m 45s
  Frame distribution: CAUSAL (35%), CONSTRAINT (22%), PATTERN (18%), PROCEDURE (15%), TAXONOMY (10%)
  Confidence: avg=0.91, min=0.60, max=1.00
```

## Error Handling & Recovery

- **Crawl timeout**: Offer retry with lower limit or different URL
- **Invalid path**: Show `ls` output, offer to correct path
- **KB conflict**: Offer append or replace
- **Hang detection**: If no progress for 2+ min, offer cancel + retry with smaller limit

After recovery, re-run and show updated stats.

## Skill Structure

File: `/Users/emmahyde/.claude/plugins/semantic-memory/skills/add-knowledge-base.md`

Frontmatter:
```yaml
name: add-knowledge-base
description: Interactively create and ingest a knowledge base from crawled URLs, single pages, or Firecrawl JSON folders with real-time progress and detailed statistics
```

Content uses `AskUserQuestion`, `Bash`, parameter validation, and stats parsing.
