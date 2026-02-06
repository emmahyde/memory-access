import pytest
import numpy as np
from semantic_memory.storage import InsightStore, _migrate_003_insight_relations
from semantic_memory.models import Frame, Insight


class TestInsightStoreInit:
    async def test_initialize_creates_tables(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        # Verify table exists by inserting
        insight = Insight(
            text="test insight",
            normalized_text="test insight normalized",
            frame=Frame.CAUSAL,
        )
        insight_id = await store.insert(insight)
        assert isinstance(insight_id, str)
        assert len(insight_id) == 36  # UUID length


class TestInsightStoreInsert:
    async def test_insert_minimal_insight(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="test", normalized_text="test", frame=Frame.CAUSAL)
        insight_id = await store.insert(insight)
        assert insight_id is not None

    async def test_insert_with_embedding(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="test", normalized_text="test", frame=Frame.CAUSAL)
        embedding = np.random.randn(384).astype(np.float32)
        insight_id = await store.insert(insight, embedding=embedding)
        assert insight_id is not None

    async def test_insert_preserves_all_fields(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(
            text="original text",
            normalized_text="state mutation causes re-render skip",
            frame=Frame.CAUSAL,
            domains=["react", "frontend"],
            entities=["React", "state"],
            confidence=0.9,
            source="debug_session",
        )
        insight_id = await store.insert(insight)
        retrieved = await store.get(insight_id)
        assert retrieved is not None
        assert retrieved.text == "original text"
        assert retrieved.normalized_text == "state mutation causes re-render skip"
        assert retrieved.frame == Frame.CAUSAL
        assert retrieved.domains == ["react", "frontend"]
        assert retrieved.entities == ["React", "state"]
        assert retrieved.confidence == 0.9
        assert retrieved.source == "debug_session"


class TestInsightStoreUpdate:
    async def test_update_text_fields(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="old", normalized_text="old", frame=Frame.CAUSAL)
        iid = await store.insert(insight)
        updated = await store.update(iid, normalized_text="new", confidence=0.5)
        assert updated is not None
        assert updated.normalized_text == "new"
        assert updated.confidence == 0.5
        assert updated.text == "old"  # unchanged

    async def test_update_nonexistent_returns_none(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        result = await store.update("nonexistent-id", confidence=0.1)
        assert result is None


class TestInsightStoreDelete:
    async def test_delete_existing(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="delete me", normalized_text="delete me", frame=Frame.CAUSAL)
        iid = await store.insert(insight)
        deleted = await store.delete(iid)
        assert deleted is True
        assert await store.get(iid) is None

    async def test_delete_nonexistent(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        deleted = await store.delete("nonexistent-id")
        assert deleted is False


class TestInsightStoreSearch:
    async def test_search_by_embedding_returns_ranked(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # Create two insights with known embeddings
        emb_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        await store.insert(
            Insight(text="a", normalized_text="a", frame=Frame.CAUSAL), embedding=emb_a
        )
        await store.insert(
            Insight(text="b", normalized_text="b", frame=Frame.CAUSAL), embedding=emb_b
        )

        # Query closer to emb_a
        query = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        results = await store.search_by_embedding(query, limit=2)

        assert len(results) == 2
        assert results[0].insight.text == "a"
        assert results[0].score > results[1].score

    async def test_search_with_domain_filter(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        await store.insert(
            Insight(text="react thing", normalized_text="r", frame=Frame.CAUSAL, domains=["react"]),
            embedding=emb,
        )
        await store.insert(
            Insight(text="python thing", normalized_text="p", frame=Frame.CAUSAL, domains=["python"]),
            embedding=emb,
        )

        results = await store.search_by_embedding(emb, limit=10, domain="react")
        assert len(results) == 1
        assert results[0].insight.text == "react thing"

    async def test_search_empty_db(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = await store.search_by_embedding(query)
        assert results == []


class TestMigrationInfrastructure:
    async def test_initialize_creates_schema_versions(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_versions'"
            )
            row = await cursor.fetchone()
            assert row is not None

    async def test_schema_version_starts_at_zero(self, tmp_db):
        store = InsightStore(tmp_db)
        store._migrations = []  # Clear migrations for this test
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute("SELECT MAX(version) FROM schema_versions")
            row = await cursor.fetchone()
            assert row[0] is None  # no migrations applied yet

    async def test_migrations_run_in_order(self, tmp_db):
        """Register two test migrations and verify they run in order."""
        store = InsightStore(tmp_db)

        call_order = []
        async def mig_001(db):
            call_order.append(1)
            return "test migration 1"
        async def mig_002(db):
            call_order.append(2)
            return "test migration 2"

        store._migrations = [(1, mig_001), (2, mig_002)]
        await store.initialize()

        assert call_order == [1, 2]

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute("SELECT version, description FROM schema_versions ORDER BY version")
            rows = await cursor.fetchall()
            assert len(rows) == 2
            assert rows[0][0] == 1
            assert rows[1][0] == 2

    async def test_migrations_are_idempotent(self, tmp_db):
        """Running initialize() twice should not re-run migrations."""
        store = InsightStore(tmp_db)

        run_count = 0
        async def mig_001(db):
            nonlocal run_count
            run_count += 1
            return "test migration"

        store._migrations = [(1, mig_001)]
        await store.initialize()
        await store.initialize()

        assert run_count == 1

    async def test_existing_insights_survive_migration(self, tmp_db):
        """Migrations should not destroy existing data."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(text="survive", normalized_text="survive", frame=Frame.CAUSAL)
        iid = await store.insert(insight)

        # Add a migration and re-initialize
        async def mig_001(db):
            return "harmless migration"
        store._migrations = [(1, mig_001)]
        await store.initialize()

        retrieved = await store.get(iid)
        assert retrieved is not None
        assert retrieved.text == "survive"


class TestSubjectIndex:
    async def test_migration_001_creates_tables(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'"
            )
            assert await cursor.fetchone() is not None
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='insight_subjects'"
            )
            assert await cursor.fetchone() is not None

    async def test_migration_001_backfills_domains(self, tmp_db):
        store = InsightStore(tmp_db)
        # Temporarily remove migration to insert raw data first
        saved_migrations = store._migrations
        store._migrations = []
        await store.initialize()

        insight = Insight(
            text="test", normalized_text="test", frame=Frame.CAUSAL,
            domains=["react", "frontend"], entities=["React"]
        )
        await store.insert(insight)

        # Now apply migration
        store._migrations = saved_migrations
        await store.initialize()

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM subjects ORDER BY name")
            rows = await cursor.fetchall()
            subjects = [(r["name"], r["kind"]) for r in rows]
            assert ("react", "domain") in subjects
            assert ("frontend", "domain") in subjects
            assert ("react", "entity") in subjects  # React entity (lowercased)

    async def test_insert_maintains_subjects(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="new", normalized_text="new", frame=Frame.PATTERN,
            domains=["python", "testing"], entities=["pytest"]
        )
        await store.insert(insight)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT name, kind FROM subjects ORDER BY name")
            rows = await cursor.fetchall()
            subjects = [(r["name"], r["kind"]) for r in rows]
            assert ("python", "domain") in subjects
            assert ("testing", "domain") in subjects
            assert ("pytest", "entity") in subjects

            # Verify join table
            cursor = await db.execute("SELECT COUNT(*) FROM insight_subjects")
            row = await cursor.fetchone()
            assert row[0] == 3  # 2 domains + 1 entity

    async def test_insert_deduplicates_subjects(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        for _ in range(3):
            insight = Insight(
                text="dup", normalized_text="dup", frame=Frame.CAUSAL,
                domains=["python"], entities=[]
            )
            await store.insert(insight)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM subjects WHERE name='python'")
            row = await cursor.fetchone()
            assert row[0] == 1  # deduplicated

    async def test_search_by_subject(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        i1 = Insight(text="python stuff", normalized_text="python stuff", frame=Frame.PATTERN, domains=["python"])
        i2 = Insight(text="rust stuff", normalized_text="rust stuff", frame=Frame.PATTERN, domains=["rust"])
        await store.insert(i1)
        await store.insert(i2)

        results = await store.search_by_subject("python")
        assert len(results) == 1
        assert results[0].text == "python stuff"

    async def test_search_by_subject_with_kind_filter(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # "react" as both domain and entity
        insight = Insight(
            text="react", normalized_text="react", frame=Frame.CAUSAL,
            domains=["react"], entities=["React"]  # React lowercases to "react"
        )
        await store.insert(insight)

        # Search without kind filter — should find it
        results = await store.search_by_subject("react")
        assert len(results) == 1

        # Search with kind filter
        results = await store.search_by_subject("react", kind="domain")
        assert len(results) == 1
        results = await store.search_by_subject("react", kind="entity")
        assert len(results) == 1

    async def test_insert_creates_problem_and_resolution_subjects(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="fixed it", normalized_text="fixed it", frame=Frame.CAUSAL,
            domains=["backend"], entities=["Redis"],
            problems=["memory leak"], resolutions=["restart service"],
            contexts=["production"],
        )
        await store.insert(insight)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT name, kind FROM subjects ORDER BY kind, name")
            rows = await cursor.fetchall()
            subjects = [(r["name"], r["kind"]) for r in rows]
            assert ("production", "context") in subjects
            assert ("backend", "domain") in subjects
            assert ("redis", "entity") in subjects
            assert ("memory leak", "problem") in subjects
            assert ("restart service", "resolution") in subjects


class TestInsightRelations:
    async def test_migration_003_creates_table(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='insight_relations'"
            )
            assert await cursor.fetchone() is not None

    async def test_backfill_creates_relations_for_shared_subjects(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # Two insights sharing "python" domain
        i1 = Insight(text="a", normalized_text="a", frame=Frame.CAUSAL, domains=["python"], entities=["pytest"])
        i2 = Insight(text="b", normalized_text="b", frame=Frame.PATTERN, domains=["python"], entities=["mypy"])
        id1 = await store.insert(i1)
        id2 = await store.insert(i2)

        # Force re-run of migration 003 backfill by calling it directly
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            await _migrate_003_insight_relations(db)
            cursor = await db.execute(
                "SELECT * FROM insight_relations WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
                (id1, id2, id2, id1)
            )
            rows = await cursor.fetchall()
            assert len(rows) >= 1
            # They share "python" domain subject
            assert any(r[2] == "shared_subject" for r in rows)

    async def test_related_insights_returns_connected(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        i1 = Insight(text="insight A", normalized_text="A", frame=Frame.CAUSAL,
                     domains=["devops"], problems=["memory leak"])
        i2 = Insight(text="insight B", normalized_text="B", frame=Frame.PROCEDURE,
                     domains=["devops"], resolutions=["restart service"])
        i3 = Insight(text="insight C", normalized_text="C", frame=Frame.PATTERN,
                     domains=["frontend"])  # no overlap

        id1 = await store.insert(i1)
        id2 = await store.insert(i2)
        id3 = await store.insert(i3)

        # Build relations
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            await _migrate_003_insight_relations(db)

        results = await store.related_insights(id1, limit=10)
        related_ids = [r.insight.id for r in results]
        assert id2 in related_ids  # shares "devops"
        assert id3 not in related_ids  # no shared subjects

    async def test_related_insights_empty(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        i1 = Insight(text="lonely", normalized_text="lonely", frame=Frame.CAUSAL, domains=["unique_domain"])
        id1 = await store.insert(i1)

        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            await _migrate_003_insight_relations(db)

        results = await store.related_insights(id1)
        assert results == []


class TestSubjectRelations:
    async def test_migration_creates_subject_relations_table(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='subject_relations'"
            )
            assert await cursor.fetchone() is not None

    async def test_add_subject_relation(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # Create two subjects manually
        import aiosqlite
        import uuid
        now = "2026-02-06T00:00:00+00:00"
        repo_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "repo:semantic-memory"))
        project_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "project:schema-evolution"))

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, 'repo', ?)",
                (repo_id, "semantic-memory", now)
            )
            await db.execute(
                "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, 'project', ?)",
                (project_id, "schema-evolution", now)
            )
            await db.commit()

        await store.add_subject_relation(
            from_name="semantic-memory", from_kind="repo",
            to_name="schema-evolution", to_kind="project",
            relation_type="contains"
        )

        relations = await store.get_subject_relations("semantic-memory", kind="repo")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "schema-evolution"
        assert relations[0]["relation_type"] == "contains"

    async def test_get_subject_children(self, tmp_db):
        """Test traversing the hierarchy: repo -> project -> task"""
        store = InsightStore(tmp_db)
        await store.initialize()

        import aiosqlite
        import uuid
        now = "2026-02-06T00:00:00+00:00"

        # Create subjects
        subjects = [
            ("repo:myrepo", "myrepo", "repo"),
            ("project:auth-system", "auth-system", "project"),
            ("task:add-jwt", "add-jwt", "task"),
            ("task:add-oauth", "add-oauth", "task"),
        ]
        async with aiosqlite.connect(tmp_db) as db:
            for ns, name, kind in subjects:
                sid = str(uuid.uuid5(uuid.NAMESPACE_DNS, ns))
                await db.execute(
                    "INSERT OR IGNORE INTO subjects (id, name, kind, created_at) VALUES (?, ?, ?, ?)",
                    (sid, name, kind, now)
                )
            await db.commit()

        # Create relations
        await store.add_subject_relation("myrepo", "repo", "auth-system", "project", "contains")
        await store.add_subject_relation("auth-system", "project", "add-jwt", "task", "contains")
        await store.add_subject_relation("auth-system", "project", "add-oauth", "task", "contains")

        # Get direct children of project
        children = await store.get_subject_relations("auth-system", kind="project", relation_type="contains")
        assert len(children) == 2
        names = [c["to_name"] for c in children]
        assert "add-jwt" in names
        assert "add-oauth" in names

    async def test_problem_solved_by_resolution(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # Insert insights that have problems and resolutions
        i1 = Insight(text="leak fix", normalized_text="leak fix", frame=Frame.CAUSAL,
                     domains=["backend"], problems=["memory leak"], resolutions=["added connection pooling"])
        await store.insert(i1)

        # Now link the problem to the resolution
        await store.add_subject_relation(
            "memory leak", "problem", "added connection pooling", "resolution", "solved_by"
        )

        relations = await store.get_subject_relations("memory leak", kind="problem")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "added connection pooling"
        assert relations[0]["relation_type"] == "solved_by"
