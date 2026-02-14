from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlite3

from peewee import IntegrityError

from .models import TaskEventRecord, TaskRecord, TaskState, TransitionResult
from .orm_models import TaskDependencyModel, TaskEventModel, TaskLockModel, TaskModel, database, init_task_database


class TaskStoreError(Exception):
    """Base class for task state-machine errors."""


class TaskNotFound(TaskStoreError):
    """Task does not exist."""


class InvalidTransition(TaskStoreError):
    """State transition violates DB state-machine rules."""


class DependencyNotMet(TaskStoreError):
    """A dependency is not done, blocking in-progress transition."""


class LockConflict(TaskStoreError):
    """Resource lock conflict occurred."""


class ConcurrencyConflict(TaskStoreError):
    """Optimistic concurrency check failed."""


class TaskStore:
    """Async facade over sync Peewee operations with DB-enforced invariants."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        init_task_database(db_path)

    async def _run(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def _create_task_sync(self, task_id: str, title: str, owner: str = "") -> TaskRecord:
        now = datetime.now(timezone.utc)
        with database.connection_context():
            task = TaskModel.create(
                task_id=task_id,
                title=title,
                status=TaskState.TODO.value,
                owner=owner,
                created_at=now,
                updated_at=now,
            )
            return _task_model_to_record(task)

    async def create_task(self, title: str, owner: str = "", task_id: str | None = None) -> TaskRecord:
        return await self._run(self._create_task_sync, task_id or str(uuid.uuid4()), title, owner)

    def _assign_locks_sync(self, task_id: str, resources: list[str]) -> list[str]:
        now = datetime.now(timezone.utc)
        lock_ids: list[str] = []
        with database.connection_context():
            for resource in resources:
                if not resource:
                    continue
                lock_id = str(uuid.uuid4())
                try:
                    TaskLockModel.create(
                        id=lock_id,
                        task_id=task_id,
                        resource=resource,
                        active=True,
                        created_at=now,
                    )
                except IntegrityError as exc:
                    raise LockConflict(str(exc)) from exc
                lock_ids.append(lock_id)
        return lock_ids

    async def assign_locks(self, task_id: str, resources: list[str]) -> list[str]:
        return await self._run(self._assign_locks_sync, task_id, resources)

    def _add_dependencies_sync(self, task_id: str, depends_on_task_ids: list[str]) -> None:
        with database.connection_context():
            for dep_id in depends_on_task_ids:
                if not dep_id:
                    continue
                TaskDependencyModel.insert(
                    task_id=task_id,
                    depends_on_task_id=dep_id,
                ).on_conflict_ignore().execute()

    async def add_dependencies(self, task_id: str, depends_on_task_ids: list[str]) -> None:
        await self._run(self._add_dependencies_sync, task_id, depends_on_task_ids)

    def _append_event_sync(self, task_id: str, event_type: str, actor: str, payload: dict[str, Any] | None = None) -> TaskEventRecord:
        now = datetime.now(timezone.utc)
        payload_json = json.dumps(payload or {})
        with database.connection_context():
            event = TaskEventModel.create(
                id=str(uuid.uuid4()),
                task_id=task_id,
                event_type=event_type,
                actor=actor,
                payload=payload_json,
                created_at=now,
            )
            return _event_model_to_record(event)

    async def append_event(
        self, task_id: str, event_type: str, actor: str, payload: dict[str, Any] | None = None
    ) -> TaskEventRecord:
        return await self._run(self._append_event_sync, task_id, event_type, actor, payload)

    def _transition_sync(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        actor: str,
        reason: str,
        evidence: str,
        expected_version: int,
    ) -> TransitionResult:
        now = datetime.now(timezone.utc)
        payload = json.dumps(
            {
                "from_state": from_state.value,
                "to_state": to_state.value,
                "reason": reason,
                "evidence": evidence,
            }
        )

        with database.connection_context():
            conn = database.connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?,
                        retry_count = CASE WHEN ? = 'blocked' THEN retry_count + 1 ELSE retry_count END,
                        version = version + 1,
                        updated_at = ?
                    WHERE task_id = ? AND status = ? AND version = ?
                    """,
                    (to_state.value, to_state.value, now.isoformat(), task_id, from_state.value, expected_version),
                )
                if cursor.rowcount != 1:
                    current = conn.execute(
                        "SELECT status, version FROM tasks WHERE task_id = ?",
                        (task_id,),
                    ).fetchone()
                    conn.rollback()
                    if current is None:
                        raise TaskNotFound(task_id)
                    if current[1] != expected_version:
                        raise ConcurrencyConflict(f"expected version {expected_version}, found {current[1]}")
                    raise InvalidTransition(f"expected {from_state.value}, found {current[0]}")

                event_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO task_events (id, task_id, event_type, actor, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, task_id, "state_transition", actor, payload, now.isoformat()),
                )

                row = conn.execute(
                    "SELECT task_id, title, status, owner, retry_count, version, created_at, updated_at FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                conn.commit()
            except (sqlite3.IntegrityError, sqlite3.OperationalError) as exc:
                conn.rollback()
                msg = str(exc)
                if "task dependencies not complete" in msg:
                    raise DependencyNotMet(msg) from exc
                if "invalid task state transition" in msg:
                    raise InvalidTransition(msg) from exc
                raise

        task = TaskRecord(
            task_id=row[0],
            title=row[1],
            status=TaskState(row[2]),
            owner=row[3],
            retry_count=row[4],
            version=row[5],
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
        )
        return TransitionResult(task=task, event_id=event_id)

    async def transition(
        self,
        task_id: str,
        from_state: TaskState,
        to_state: TaskState,
        actor: str,
        expected_version: int,
        reason: str = "",
        evidence: str = "",
    ) -> TransitionResult:
        return await self._run(
            self._transition_sync,
            task_id,
            from_state,
            to_state,
            actor,
            reason,
            evidence,
            expected_version,
        )

    def _get_task_sync(self, task_id: str) -> TaskRecord | None:
        with database.connection_context():
            task = TaskModel.get_or_none(TaskModel.task_id == task_id)
            if task is None:
                return None
            return _task_model_to_record(task)

    async def get_task(self, task_id: str) -> TaskRecord | None:
        return await self._run(self._get_task_sync, task_id)

    def _list_tasks_sync(self, status: TaskState | None = None, limit: int = 100) -> list[TaskRecord]:
        with database.connection_context():
            query = TaskModel.select().order_by(TaskModel.created_at.desc()).limit(limit)
            if status is not None:
                query = query.where(TaskModel.status == status.value)
            return [_task_model_to_record(task) for task in query]

    async def list_tasks(self, status: TaskState | None = None, limit: int = 100) -> list[TaskRecord]:
        return await self._run(self._list_tasks_sync, status, limit)


def _task_model_to_record(task: TaskModel) -> TaskRecord:
    return TaskRecord(
        task_id=task.task_id,
        title=task.title,
        status=TaskState(task.status),
        owner=task.owner,
        retry_count=task.retry_count,
        version=task.version,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _event_model_to_record(event: TaskEventModel) -> TaskEventRecord:
    payload = json.loads(event.payload) if event.payload else {}
    return TaskEventRecord(
        id=event.id,
        task_id=event.task_id,
        event_type=event.event_type,
        actor=event.actor,
        payload=payload,
        created_at=event.created_at,
    )
