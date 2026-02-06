import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import numpy as np

from .models import Frame, Insight, SearchResult

SCHEMA = """\
CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    frame TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',
    entities TEXT NOT NULL DEFAULT '[]',
    problems TEXT NOT NULL DEFAULT '[]',
    resolutions TEXT NOT NULL DEFAULT '[]',
    contexts TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_frame ON insights(frame);
"""

SCHEMA_VERSIONS = """\
CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT NOT NULL
);
"""


async def _migrate_002_add_extraction_columns(db: aiosqlite.Connection) -> str:
    """Add problems, resolutions, contexts columns to insights table."""
    # Check if columns already exist (they may be in SCHEMA for new DBs)
    cursor = await db.execute("PRAGMA table_info(insights)")
    columns = [row[1] for row in await cursor.fetchall()]

    if "problems" not in columns:
        await db.execute("ALTER TABLE insights ADD COLUMN problems TEXT NOT NULL DEFAULT '[]'")
    if "resolutions" not in columns:
        await db.execute("ALTER TABLE insights ADD COLUMN resolutions TEXT NOT NULL DEFAULT '[]'")
    if "contexts" not in columns:
        await db.execute("ALTER TABLE insights ADD COLUMN contexts TEXT NOT NULL DEFAULT '[]'")

    await db.commit()
    return "Add problems, resolutions, contexts columns to insights"


async def _migrate_003_insight_relations(db: aiosqlite.Connection) -> str:
    """Create insight_relations table and backfill from shared subjects."""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS insight_relations (
            from_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
            to_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (from_id, to_id, relation_type)
        );
        CREATE INDEX IF NOT EXISTS idx_relations_from ON insight_relations(from_id);
        CREATE INDEX IF NOT EXISTS idx_relations_to ON insight_relations(to_id);
    """)
    await db.commit()

    # Backfill: find insight pairs sharing subjects
    # For each pair of insights that share at least one subject,
    # create a shared_subject relation with weight = number of shared subjects
    now = datetime.now(timezone.utc).isoformat()

    cursor = await db.execute("""
        SELECT a.insight_id, b.insight_id, COUNT(*) as shared_count
        FROM insight_subjects a
        JOIN insight_subjects b ON a.subject_id = b.subject_id AND a.insight_id < b.insight_id
        GROUP BY a.insight_id, b.insight_id
        HAVING shared_count >= 1
    """)
    rows = await cursor.fetchall()

    for row in rows:
        await db.execute(
            "INSERT OR IGNORE INTO insight_relations (from_id, to_id, relation_type, weight, created_at) VALUES (?, ?, 'shared_subject', ?, ?)",
            (row[0], row[1], float(row[2]), now),
        )

    await db.commit()
    return "Add insight_relations table with shared-subject backfill"


async def _migrate_004_subject_relations(db: aiosqlite.Connection) -> str:
    """Create subject_relations table for subject hierarchy."""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS subject_relations (
            from_subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            to_subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (from_subject_id, to_subject_id, relation_type)
        );
        CREATE INDEX IF NOT EXISTS idx_subrel_from ON subject_relations(from_subject_id);
        CREATE INDEX IF NOT EXISTS idx_subrel_to ON subject_relations(to_subject_id);
        CREATE INDEX IF NOT EXISTS idx_subrel_type ON subject_relations(relation_type);
    """)
    await db.commit()
    return "Add subject_relations table for subject hierarchy"


async def _migrate_001_subject_index(db: aiosqlite.Connection) -> str:
    """Create subjects and insight_subjects tables, backfill from existing data."""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(name, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_subjects_name ON subjects(name);
        CREATE INDEX IF NOT EXISTS idx_subjects_kind ON subjects(kind);

        CREATE TABLE IF NOT EXISTS insight_subjects (
            insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
            subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            PRIMARY KEY (insight_id, subject_id)
        );
        CREATE INDEX IF NOT EXISTS idx_insight_subjects_subject ON insight_subjects(subject_id);
    """)
    await db.commit()

    # Backfill from existing insights
    cursor = await db.execute("SELECT id, domains, entities FROM insights")
    rows = await cursor.fetchall()

    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        insight_id = row[0]
        domains = json.loads(row[1]) if row[1] else []
        entities = json.loads(row[2]) if row[2] else []

        for domain in domains:
            name = domain.strip().lower()
            if not name:
                continue
            subject_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"domain:{name}"))
            await db.execute(
                "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, 'domain', ?)",
                (subject_id, name, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO insight_subjects (insight_id, subject_id) VALUES (?, ?)",
                (insight_id, subject_id),
            )

        for entity in entities:
            name = entity.strip().lower()
            if not name:
                continue
            subject_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"entity:{name}"))
            await db.execute(
                "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, 'entity', ?)",
                (subject_id, name, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO insight_subjects (insight_id, subject_id) VALUES (?, ?)",
                (insight_id, subject_id),
            )

    await db.commit()
    return "Add subjects table and insight_subjects join table with backfill"


class InsightStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._migrations: list = [(1, _migrate_001_subject_index), (2, _migrate_002_add_extraction_columns), (3, _migrate_003_insight_relations), (4, _migrate_004_subject_relations)]  # list[tuple[int, Callable]]

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.executescript(SCHEMA_VERSIONS)
            await db.commit()

            # Run pending migrations
            cursor = await db.execute("SELECT MAX(version) FROM schema_versions")
            row = await cursor.fetchone()
            current_version = row[0] if row[0] is not None else 0

            for version, migrate_fn in sorted(self._migrations):
                if version > current_version:
                    description = await migrate_fn(db)
                    now = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        "INSERT INTO schema_versions (version, applied_at, description) VALUES (?, ?, ?)",
                        (version, now, description or f"migration {version}"),
                    )
                    await db.commit()

    async def _upsert_subjects(self, db, insight_id: str, insight: Insight):
        """Maintain subjects and insight_subjects tables on insert."""
        now = datetime.now(timezone.utc).isoformat()

        for kind, items in [
            ("domain", insight.domains),
            ("entity", insight.entities),
            ("problem", insight.problems),
            ("resolution", insight.resolutions),
            ("context", insight.contexts),
        ]:
            for item in items:
                name = item.strip().lower()
                if not name:
                    continue
                subject_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{kind}:{name}"))
                await db.execute(
                    "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, ?, ?)",
                    (subject_id, name, kind, now),
                )
                await db.execute(
                    "INSERT OR IGNORE INTO insight_subjects (insight_id, subject_id) VALUES (?, ?)",
                    (insight_id, subject_id),
                )

    async def insert(self, insight: Insight, embedding: np.ndarray | None = None) -> str:
        insight_id = insight.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        embedding_bytes = embedding.tobytes() if embedding is not None else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO insights
                   (id, text, normalized_text, frame, domains, entities, problems, resolutions, contexts,
                    confidence, source, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    insight_id,
                    insight.text,
                    insight.normalized_text,
                    insight.frame.value,
                    json.dumps(insight.domains),
                    json.dumps(insight.entities),
                    json.dumps(insight.problems),
                    json.dumps(insight.resolutions),
                    json.dumps(insight.contexts),
                    insight.confidence,
                    insight.source,
                    embedding_bytes,
                    now,
                    now,
                ),
            )

            # Check if subjects table exists (migration may not have run yet)
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'"
            )
            if await cursor.fetchone():
                await self._upsert_subjects(db, insight_id, insight)

            await db.commit()
        return insight_id

    async def get(self, insight_id: str) -> Insight | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM insights WHERE id = ?", (insight_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_insight(row)

    async def update(self, insight_id: str, **kwargs) -> Insight | None:
        existing = await self.get(insight_id)
        if existing is None:
            return None

        allowed = {"text", "normalized_text", "frame", "domains", "entities", "problems", "resolutions", "contexts", "confidence", "source"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return existing

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = []
        values = []
        for key, value in updates.items():
            if key in ("domains", "entities", "problems", "resolutions", "contexts"):
                value = json.dumps(value)
            elif key == "frame":
                value = value.value if isinstance(value, Frame) else value
            set_clauses.append(f"{key} = ?")
            values.append(value)

        set_clauses.append("updated_at = ?")
        values.append(now)
        values.append(insight_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE insights SET {', '.join(set_clauses)} WHERE id = ?",
                values,
            )
            await db.commit()

        return await self.get(insight_id)

    async def delete(self, insight_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM insights WHERE id = ?", (insight_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def search_by_embedding(
        self,
        query_embedding: np.ndarray,
        limit: int = 5,
        domain: str | None = None,
    ) -> list[SearchResult]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if domain:
                cursor = await db.execute(
                    "SELECT * FROM insights WHERE embedding IS NOT NULL AND domains LIKE ?",
                    (f'%"{domain}"%',),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM insights WHERE embedding IS NOT NULL"
                )

            rows = await cursor.fetchall()

        results = []
        for row in rows:
            stored_emb = np.frombuffer(row["embedding"], dtype=np.float32)
            norm_q = np.linalg.norm(query_embedding)
            norm_s = np.linalg.norm(stored_emb)
            if norm_q == 0 or norm_s == 0:
                continue
            score = float(np.dot(query_embedding, stored_emb) / (norm_q * norm_s))
            results.append(SearchResult(insight=_row_to_insight(row), score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def list_all(
        self, domain: str | None = None, frame: str | None = None, limit: int = 20
    ) -> list[Insight]:
        conditions = []
        params = []
        if domain:
            conditions.append('domains LIKE ?')
            params.append(f'%"{domain}"%')
        if frame:
            conditions.append("frame = ?")
            params.append(frame)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM insights{where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_row_to_insight(row) for row in rows]

    async def search_by_subject(
        self, name: str, kind: str | None = None, limit: int = 20
    ) -> list[Insight]:
        name = name.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if kind:
                cursor = await db.execute(
                    """SELECT i.* FROM insights i
                       JOIN insight_subjects isub ON i.id = isub.insight_id
                       JOIN subjects s ON isub.subject_id = s.id
                       WHERE s.name = ? AND s.kind = ?
                       ORDER BY i.created_at DESC LIMIT ?""",
                    (name, kind, limit),
                )
            else:
                cursor = await db.execute(
                    """SELECT DISTINCT i.* FROM insights i
                       JOIN insight_subjects isub ON i.id = isub.insight_id
                       JOIN subjects s ON isub.subject_id = s.id
                       WHERE s.name = ?
                       ORDER BY i.created_at DESC LIMIT ?""",
                    (name, limit),
                )
            rows = await cursor.fetchall()
            return [_row_to_insight(row) for row in rows]

    async def related_insights(
        self, insight_id: str, limit: int = 10
    ) -> list[SearchResult]:
        """Find insights related to the given one via shared subjects."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT i.*, r.weight as rel_weight FROM insights i
                   JOIN insight_relations r ON (
                       (r.from_id = ? AND r.to_id = i.id) OR
                       (r.to_id = ? AND r.from_id = i.id)
                   )
                   ORDER BY r.weight DESC
                   LIMIT ?""",
                (insight_id, insight_id, limit),
            )
            rows = await cursor.fetchall()
            return [SearchResult(insight=_row_to_insight(row), score=float(row["rel_weight"])) for row in rows]

    async def add_subject_relation(
        self, from_name: str, from_kind: str,
        to_name: str, to_kind: str,
        relation_type: str,
    ) -> bool:
        """Create a directed relation between two subjects."""
        from_name = from_name.strip().lower()
        to_name = to_name.strip().lower()
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # Find subject IDs
            cursor = await db.execute(
                "SELECT id FROM subjects WHERE name = ? AND kind = ?",
                (from_name, from_kind)
            )
            from_row = await cursor.fetchone()
            if not from_row:
                return False

            cursor = await db.execute(
                "SELECT id FROM subjects WHERE name = ? AND kind = ?",
                (to_name, to_kind)
            )
            to_row = await cursor.fetchone()
            if not to_row:
                return False

            await db.execute(
                "INSERT OR IGNORE INTO subject_relations (from_subject_id, to_subject_id, relation_type, created_at) VALUES (?, ?, ?, ?)",
                (from_row[0], to_row[0], relation_type, now),
            )
            await db.commit()
        return True

    async def get_subject_relations(
        self, name: str, kind: str | None = None, relation_type: str | None = None, limit: int = 50,
    ) -> list[dict]:
        """Get relations from a subject. Returns list of dicts with to_name, to_kind, relation_type."""
        name = name.strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            conditions = ["sf.name = ?"]
            params: list = [name]

            if kind:
                conditions.append("sf.kind = ?")
                params.append(kind)
            if relation_type:
                conditions.append("sr.relation_type = ?")
                params.append(relation_type)

            params.append(limit)

            query = f"""
                SELECT st.name as to_name, st.kind as to_kind, sr.relation_type
                FROM subject_relations sr
                JOIN subjects sf ON sr.from_subject_id = sf.id
                JOIN subjects st ON sr.to_subject_id = st.id
                WHERE {' AND '.join(conditions)}
                LIMIT ?
            """

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [{"to_name": r["to_name"], "to_kind": r["to_kind"], "relation_type": r["relation_type"]} for r in rows]


def _row_to_insight(row) -> Insight:
    return Insight(
        id=row["id"],
        text=row["text"],
        normalized_text=row["normalized_text"],
        frame=Frame(row["frame"]),
        domains=json.loads(row["domains"]),
        entities=json.loads(row["entities"]),
        problems=json.loads(row["problems"]) if row["problems"] else [],
        resolutions=json.loads(row["resolutions"]) if row["resolutions"] else [],
        contexts=json.loads(row["contexts"]) if row["contexts"] else [],
        confidence=row["confidence"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
