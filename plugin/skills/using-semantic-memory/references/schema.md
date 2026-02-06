# Semantic Memory Schema Reference

## Tables (6 total, 4 migrations)

### insights (base table)
```sql
CREATE TABLE insights (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    frame TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',     -- JSON array
    entities TEXT NOT NULL DEFAULT '[]',    -- JSON array
    problems TEXT NOT NULL DEFAULT '[]',    -- JSON array (migration 002)
    resolutions TEXT NOT NULL DEFAULT '[]', -- JSON array (migration 002)
    contexts TEXT NOT NULL DEFAULT '[]',    -- JSON array (migration 002)
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT '',
    embedding BLOB,                         -- float32 vector, 1536 dims (~6KB)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### subjects (migration 001)
```sql
CREATE TABLE subjects (
    id TEXT PRIMARY KEY,            -- uuid5(NAMESPACE_DNS, "{kind}:{name}")
    name TEXT NOT NULL,
    kind TEXT NOT NULL,             -- domain|entity|problem|resolution|context|person|project|task|pr|repo
    created_at TEXT NOT NULL,
    UNIQUE(name, kind)              -- "react" can be both domain and entity
);
```

### insight_subjects (migration 001)
```sql
CREATE TABLE insight_subjects (
    insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (insight_id, subject_id)
);
```

### insight_relations (migration 003)
```sql
CREATE TABLE insight_relations (
    from_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,     -- "shared_subjects"
    weight REAL NOT NULL DEFAULT 1.0, -- count of shared subjects
    created_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_id, to_id, relation_type)
);
```

### subject_relations (migration 004)
```sql
CREATE TABLE subject_relations (
    from_subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    to_subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,     -- contains|scopes|frames|solved_by|implemented_in|etc
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_subject_id, to_subject_id, relation_type)
);
```

### schema_versions (migration infrastructure)
```sql
CREATE TABLE schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL
);
```

## Migration History

| # | Description | Commit |
|---|-------------|--------|
| 001 | Subject index (subjects + insight_subjects) | a6aff0a |
| 002 | Extraction columns (problems, resolutions, contexts on insights) | 4b83908 |
| 003 | Insight relations (shared-subject graph) | b405e69 |
| 004 | Subject relations (typed hierarchy) | 3b0fada |

## Embeddings

- Model: OpenAI text-embedding-3-small
- Dimensions: 1536
- Storage: float32 BLOB (~6KB per row)
- Search: cosine similarity (full-table scan in Python)

## Semantic Frames

| Frame | Purpose | Example |
|-------|---------|---------|
| causal | Cause-effect relationships | "Using useRef prevents re-render loops because..." |
| constraint | Limitations and boundaries | "SQLite doesn't support concurrent writes" |
| pattern | Recurring approaches | "The repository pattern isolates data access" |
| equivalence | Interchangeable concepts | "asyncio.gather is equivalent to Promise.all" |
| taxonomy | Classification hierarchies | "FastAPI is a Python web framework" |
| procedure | Step-by-step processes | "To deploy, first build then push to registry" |

## Measured Statistics (1000-row test DB)

- 104 subjects: 13 domain, 29 entity, 23 problem, 20 resolution, 19 context
- 6,771 insight-subject mappings (~6.8 per insight)
- Subject-based search: 1.5-4.3x faster than LIKE queries
- DB size: ~16MB (dominated by embedding BLOBs)
- ~1.85 domains/insight, ~2.42 entities/insight average
