import pytest
import numpy as np
from sem_mem.storage import InsightStore, _migrate_003_insight_relations
from sem_mem.models import Frame, Insight


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


class TestAutoRelateSubjects:
    async def test_auto_relate_problem_resolution(self, tmp_db):
        """Test that problem + resolution creates solved_by edge."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="fixed memory leak",
            normalized_text="fixed memory leak",
            frame=Frame.CAUSAL,
            problems=["memory leak"],
            resolutions=["added connection pooling"],
        )
        await store.insert(insight)

        # Check that the solved_by relation was auto-created
        relations = await store.get_subject_relations("memory leak", kind="problem")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "added connection pooling"
        assert relations[0]["relation_type"] == "solved_by"

    async def test_auto_relate_context_problem(self, tmp_db):
        """Test that context + problem creates frames edge."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="high load causes timeouts",
            normalized_text="high load causes timeouts",
            frame=Frame.CAUSAL,
            contexts=["high load"],
            problems=["timeouts"],
        )
        await store.insert(insight)

        # Check that the frames relation was auto-created
        relations = await store.get_subject_relations("high load", kind="context")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "timeouts"
        assert relations[0]["relation_type"] == "frames"

    async def test_auto_relate_domain_entity(self, tmp_db):
        """Test that domain + entity creates scopes edge."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="backend authentication flow",
            normalized_text="backend authentication flow",
            frame=Frame.PROCEDURE,
            domains=["backend"],
            entities=["auth service"],
        )
        await store.insert(insight)

        # Check that the scopes relation was auto-created
        relations = await store.get_subject_relations("backend", kind="domain")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "auth service"
        assert relations[0]["relation_type"] == "scopes"

    async def test_auto_relate_cartesian_product(self, tmp_db):
        """Test that multiple items create Cartesian product of edges."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="fixed multiple issues",
            normalized_text="fixed multiple issues",
            frame=Frame.CAUSAL,
            problems=["memory leak", "race condition"],
            resolutions=["connection pooling", "mutex lock", "async queue"],
        )
        await store.insert(insight)

        # Check memory leak has 3 resolutions (Cartesian product)
        relations = await store.get_subject_relations("memory leak", kind="problem")
        assert len(relations) == 3
        resolution_names = {r["to_name"] for r in relations}
        assert resolution_names == {"connection pooling", "mutex lock", "async queue"}
        assert all(r["relation_type"] == "solved_by" for r in relations)

        # Check race condition also has 3 resolutions
        relations = await store.get_subject_relations("race condition", kind="problem")
        assert len(relations) == 3
        resolution_names = {r["to_name"] for r in relations}
        assert resolution_names == {"connection pooling", "mutex lock", "async queue"}
        assert all(r["relation_type"] == "solved_by" for r in relations)


class TestGitContextSubjects:
    async def test_repo_project_creates_contains_relation(self, tmp_db):
        """Test that repo + project creates repo→contains→project relation."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="test insight",
            normalized_text="test insight",
            frame=Frame.CAUSAL,
        )
        await store.insert(insight, repo="semantic-memory", project="mcp-server")

        # Check that the contains relation was created
        relations = await store.get_subject_relations("semantic-memory", kind="repo")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "mcp-server"
        assert relations[0]["relation_type"] == "contains"

    async def test_author_pr_creates_authors_relation(self, tmp_db):
        """Test that author + pr creates person→authors→pr relation."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="test insight",
            normalized_text="test insight",
            frame=Frame.CAUSAL,
        )
        await store.insert(insight, author="alice", pr="PR-123")

        # Check that the authors relation was created
        relations = await store.get_subject_relations("alice", kind="person")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "pr-123"
        assert relations[0]["relation_type"] == "authors"

    async def test_task_pr_creates_produces_relation(self, tmp_db):
        """Test that task + pr creates task→produces→pr relation."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="test insight",
            normalized_text="test insight",
            frame=Frame.CAUSAL,
        )
        await store.insert(insight, task="add-auth", pr="PR-456")

        # Check that the produces relation was created
        relations = await store.get_subject_relations("add-auth", kind="task")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "pr-456"
        assert relations[0]["relation_type"] == "produces"

    async def test_all_git_params_creates_all_relations(self, tmp_db):
        """Test that all git params create all expected relations."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="test insight",
            normalized_text="test insight",
            frame=Frame.CAUSAL,
        )
        await store.insert(
            insight,
            repo="semantic-memory",
            project="mcp-server",
            task="add-auth",
            pr="PR-789",
            author="bob",
        )

        # Check repo→contains→project
        relations = await store.get_subject_relations("semantic-memory", kind="repo")
        assert any(r["to_name"] == "mcp-server" and r["relation_type"] == "contains" for r in relations)

        # Check project→contains→task
        relations = await store.get_subject_relations("mcp-server", kind="project")
        assert any(r["to_name"] == "add-auth" and r["relation_type"] == "contains" for r in relations)

        # Check task→produces→pr
        relations = await store.get_subject_relations("add-auth", kind="task")
        assert any(r["to_name"] == "pr-789" and r["relation_type"] == "produces" for r in relations)

        # Check person→authors→pr
        relations = await store.get_subject_relations("bob", kind="person")
        assert any(r["to_name"] == "pr-789" and r["relation_type"] == "authors" for r in relations)

        # Check person→works_on→project
        assert any(r["to_name"] == "mcp-server" and r["relation_type"] == "works_on" for r in relations)

    async def test_no_git_params_creates_no_git_subjects(self, tmp_db):
        """Test that insight without git params creates no git subjects."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="test insight",
            normalized_text="test insight",
            frame=Frame.CAUSAL,
        )
        await store.insert(insight)

        # Check that no git subjects were created
        import aiosqlite

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            for kind in ["repo", "pr", "person", "project", "task"]:
                cursor = await db.execute("SELECT COUNT(*) FROM subjects WHERE kind=?", (kind,))
                row = await cursor.fetchone()
                assert row[0] == 0

    async def test_resolution_pr_creates_implemented_in_relation(self, tmp_db):
        """Test that insight with resolution + pr creates resolution→implemented_in→pr relation."""
        store = InsightStore(tmp_db)
        await store.initialize()

        insight = Insight(
            text="fixed memory leak",
            normalized_text="fixed memory leak",
            frame=Frame.CAUSAL,
            resolutions=["added connection pooling"],
        )
        await store.insert(insight, pr="PR-999")

        # Check that the implemented_in relation was created
        relations = await store.get_subject_relations("added connection pooling", kind="resolution")
        assert len(relations) == 1
        assert relations[0]["to_name"] == "pr-999"
        assert relations[0]["relation_type"] == "implemented_in"


class TestKBMigration:
    async def test_migration_005_creates_tables(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            for table in ["knowledge_bases", "kb_chunks", "kb_chunk_subjects", "kb_insight_relations"]:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                )
                row = await cursor.fetchone()
                assert row is not None, f"Table {table} not created"


class TestKBCrud:
    async def test_create_and_get_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("rails-docs", description="Rails documentation", source_type="crawl")
        assert isinstance(kb_id, str)
        kb = await store.get_kb(kb_id)
        assert kb is not None
        assert kb.name == "rails-docs"
        assert kb.description == "Rails documentation"
        assert kb.source_type == "crawl"

    async def test_get_kb_by_name(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("python-docs")
        kb = await store.get_kb_by_name("python-docs")
        assert kb is not None
        assert kb.id == kb_id

    async def test_get_nonexistent_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        assert await store.get_kb("nonexistent") is None
        assert await store.get_kb_by_name("nonexistent") is None

    async def test_list_kbs(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        await store.create_kb("kb-a")
        await store.create_kb("kb-b")
        kbs = await store.list_kbs()
        assert len(kbs) == 2
        names = {kb.name for kb in kbs}
        assert names == {"kb-a", "kb-b"}

    async def test_delete_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("to-delete")
        assert await store.delete_kb(kb_id) is True
        assert await store.get_kb(kb_id) is None

    async def test_delete_nonexistent_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        assert await store.delete_kb("nonexistent") is False


class TestKBChunkInsert:
    async def test_insert_chunk(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk
        chunk = KbChunk(kb_id=kb_id, text="test text", normalized_text="test normalized", frame=Frame.CAUSAL, domains=["python"])
        chunk_id = await store.insert_kb_chunk(chunk)
        assert isinstance(chunk_id, str)

    async def test_insert_chunk_with_embedding(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk
        chunk = KbChunk(kb_id=kb_id, text="test", normalized_text="test", frame=Frame.CAUSAL)
        emb = np.random.randn(384).astype(np.float32)
        chunk_id = await store.insert_kb_chunk(chunk, embedding=emb)
        assert isinstance(chunk_id, str)

    async def test_insert_chunk_creates_subjects(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk
        chunk = KbChunk(
            kb_id=kb_id, text="test", normalized_text="test", frame=Frame.CAUSAL,
            domains=["react"], entities=["React"],
        )
        chunk_id = await store.insert_kb_chunk(chunk)
        import aiosqlite
        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT s.name, s.kind FROM subjects s JOIN kb_chunk_subjects kcs ON s.id = kcs.subject_id WHERE kcs.kb_chunk_id = ?",
                (chunk_id,),
            )
            rows = await cursor.fetchall()
            subjects = [(r["name"], r["kind"]) for r in rows]
            assert ("react", "domain") in subjects
            assert ("react", "entity") in subjects


class TestKBChunkSearch:
    async def test_search_within_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk

        emb_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        chunk_a = KbChunk(kb_id=kb_id, text="a", normalized_text="a", frame=Frame.CAUSAL)
        chunk_b = KbChunk(kb_id=kb_id, text="b", normalized_text="b", frame=Frame.CAUSAL)
        await store.insert_kb_chunk(chunk_a, embedding=emb_a)
        await store.insert_kb_chunk(chunk_b, embedding=emb_b)

        query = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        results = await store.search_kb_by_embedding(query, kb_id=kb_id, limit=2)
        assert len(results) == 2
        assert results[0].insight.text == "a"
        assert results[0].score > results[1].score

    async def test_search_across_all_kbs(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb1 = await store.create_kb("kb-1")
        kb2 = await store.create_kb("kb-2")
        from sem_mem.models import KbChunk

        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        await store.insert_kb_chunk(KbChunk(kb_id=kb1, text="from kb1", normalized_text="from kb1", frame=Frame.CAUSAL), embedding=emb)
        await store.insert_kb_chunk(KbChunk(kb_id=kb2, text="from kb2", normalized_text="from kb2", frame=Frame.CAUSAL), embedding=emb)

        results = await store.search_kb_by_embedding(emb, limit=10)
        assert len(results) == 2

    async def test_search_empty_kb(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("empty-kb")
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = await store.search_kb_by_embedding(query, kb_id=kb_id)
        assert results == []


class TestKBChunkList:
    async def test_list_chunks(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk
        for i in range(3):
            await store.insert_kb_chunk(KbChunk(kb_id=kb_id, text=f"chunk {i}", normalized_text=f"chunk {i}", frame=Frame.CAUSAL))
        chunks = await store.list_kb_chunks(kb_id)
        assert len(chunks) == 3


class TestKBChunkDelete:
    async def test_delete_chunks(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("test-kb")
        from sem_mem.models import KbChunk
        for i in range(3):
            await store.insert_kb_chunk(KbChunk(kb_id=kb_id, text=f"chunk {i}", normalized_text=f"chunk {i}", frame=Frame.CAUSAL))
        deleted = await store.delete_kb_chunks(kb_id)
        assert deleted == 3
        chunks = await store.list_kb_chunks(kb_id)
        assert len(chunks) == 0

    async def test_cascade_delete_removes_chunks(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        kb_id = await store.create_kb("cascade-test")
        from sem_mem.models import KbChunk
        await store.insert_kb_chunk(KbChunk(kb_id=kb_id, text="chunk", normalized_text="chunk", frame=Frame.CAUSAL, domains=["test"]))
        await store.delete_kb(kb_id)
        chunks = await store.list_kb_chunks(kb_id)
        assert len(chunks) == 0
