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
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_insights_frame ON insights(frame);
"""


class InsightStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def insert(self, insight: Insight, embedding: np.ndarray | None = None) -> str:
        insight_id = insight.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        embedding_bytes = embedding.tobytes() if embedding is not None else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO insights
                   (id, text, normalized_text, frame, domains, entities,
                    confidence, source, embedding, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    insight_id,
                    insight.text,
                    insight.normalized_text,
                    insight.frame.value,
                    json.dumps(insight.domains),
                    json.dumps(insight.entities),
                    insight.confidence,
                    insight.source,
                    embedding_bytes,
                    now,
                    now,
                ),
            )
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


def _row_to_insight(row) -> Insight:
    return Insight(
        id=row["id"],
        text=row["text"],
        normalized_text=row["normalized_text"],
        frame=Frame(row["frame"]),
        domains=json.loads(row["domains"]),
        entities=json.loads(row["entities"]),
        confidence=row["confidence"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
