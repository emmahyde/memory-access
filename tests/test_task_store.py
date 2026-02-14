import asyncio

import aiosqlite
import pytest

pytest.importorskip("peewee")

from memory_access.models import TaskState
from memory_access.storage import InsightStore
from memory_access.task_store import (
    ConcurrencyConflict,
    DependencyNotMet,
    InvalidTransition,
    LockConflict,
    TaskStore,
)


class TestTaskStore:
    async def test_create_task_defaults(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        task = await task_store.create_task(title="index docs", owner="agent-1")
        assert task.title == "index docs"
        assert task.owner == "agent-1"
        assert task.status == TaskState.TODO
        assert task.version == 0

    async def test_lock_conflict_enforced_by_db(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        t1 = await task_store.create_task("task 1")
        t2 = await task_store.create_task("task 2")

        await task_store.assign_locks(t1.task_id, ["src/a.py"])

        with pytest.raises(LockConflict):
            await task_store.assign_locks(t2.task_id, ["src/a.py"])

    async def test_lock_prefix_conflict_enforced_by_db(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        t1 = await task_store.create_task("task 1")
        t2 = await task_store.create_task("task 2")

        await task_store.assign_locks(t1.task_id, ["src"])

        with pytest.raises(LockConflict):
            await task_store.assign_locks(t2.task_id, ["src/a.py"])

    async def test_release_locks_allows_reacquire(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        t1 = await task_store.create_task("task 1")
        t2 = await task_store.create_task("task 2")

        await task_store.assign_locks(t1.task_id, ["src/a.py"])
        released = await task_store.release_locks(t1.task_id)
        assert released == 1

        lock_ids = await task_store.assign_locks(t2.task_id, ["src/a.py"])
        assert len(lock_ids) == 1

    async def test_invalid_transition_rejected(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        task = await task_store.create_task("transition test")

        with pytest.raises(InvalidTransition):
            await task_store.transition(
                task_id=task.task_id,
                from_state=TaskState.TODO,
                to_state=TaskState.DONE,
                actor="orchestrator",
                expected_version=task.version,
            )

    async def test_dependency_blocks_in_progress(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        dep = await task_store.create_task("dependency")
        main = await task_store.create_task("main")
        await task_store.add_dependencies(main.task_id, [dep.task_id])

        with pytest.raises(DependencyNotMet):
            await task_store.transition(
                task_id=main.task_id,
                from_state=TaskState.TODO,
                to_state=TaskState.IN_PROGRESS,
                actor="orchestrator",
                expected_version=main.version,
            )

    async def test_dependency_then_successful_transition(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        dep = await task_store.create_task("dependency")
        main = await task_store.create_task("main")
        await task_store.add_dependencies(main.task_id, [dep.task_id])

        dep_in_progress = await task_store.transition(
            dep.task_id,
            from_state=TaskState.TODO,
            to_state=TaskState.IN_PROGRESS,
            actor="orchestrator",
            expected_version=dep.version,
        )
        dep_done = await task_store.transition(
            dep.task_id,
            from_state=TaskState.IN_PROGRESS,
            to_state=TaskState.DONE,
            actor="orchestrator",
            expected_version=dep_in_progress.task.version,
        )
        assert dep_done.task.status == TaskState.DONE

        main_in_progress = await task_store.transition(
            main.task_id,
            from_state=TaskState.TODO,
            to_state=TaskState.IN_PROGRESS,
            actor="orchestrator",
            expected_version=main.version,
        )
        assert main_in_progress.task.status == TaskState.IN_PROGRESS

    async def test_concurrent_cas_allows_only_one_winner(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        task = await task_store.create_task("race")

        async def attempt_transition():
            return await task_store.transition(
                task_id=task.task_id,
                from_state=TaskState.TODO,
                to_state=TaskState.IN_PROGRESS,
                actor="orchestrator",
                expected_version=0,
            )

        results = await asyncio.gather(attempt_transition(), attempt_transition(), return_exceptions=True)

        success_count = sum(1 for r in results if not isinstance(r, Exception))
        conflict_count = sum(1 for r in results if isinstance(r, ConcurrencyConflict))

        assert success_count == 1
        assert conflict_count == 1

    async def test_task_events_append_only(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        task = await task_store.create_task("events")
        event = await task_store.append_event(task.task_id, "manual_note", "operator", {"message": "hello"})

        async with aiosqlite.connect(tmp_db) as db:
            with pytest.raises(aiosqlite.Error):
                await db.execute("UPDATE task_events SET event_type = 'changed' WHERE id = ?", (event.id,))
                await db.commit()

    async def test_list_events_returns_latest_first(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        task_store = TaskStore(tmp_db)

        task = await task_store.create_task("events")
        await task_store.append_event(task.task_id, "first", "operator", {"i": 1})
        await task_store.append_event(task.task_id, "second", "operator", {"i": 2})

        events = await task_store.list_events(task.task_id, limit=2)
        assert [event.event_type for event in events] == ["second", "first"]

    async def test_migration_created_task_tables(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
            assert await cursor.fetchone() is not None
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_events'")
            assert await cursor.fetchone() is not None
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='ux_task_locks_active_resource'"
            )
            assert await cursor.fetchone() is not None
            cursor = await db.execute("SELECT MAX(version) FROM schema_versions")
            row = await cursor.fetchone()
            assert row is not None and row[0] >= 7
