from __future__ import annotations

from peewee import BooleanField, CharField, CompositeKey, DateTimeField, IntegerField, Model, SqliteDatabase, TextField

# New connections inherit pragmatic SQLite settings for consistency and lock behavior.
database = SqliteDatabase(
    None,
    pragmas={
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": 5000,
    },
)


class TaskModel(Model):
    task_id = CharField(primary_key=True)
    title = TextField()
    status = CharField()
    owner = CharField(default="")
    retry_count = IntegerField(default=0)
    version = IntegerField(default=0)
    created_at = DateTimeField()
    updated_at = DateTimeField()

    class Meta:
        table_name = "tasks"


class TaskLockModel(Model):
    id = CharField(primary_key=True)
    task_id = CharField()
    resource = TextField()
    active = BooleanField(default=True)
    created_at = DateTimeField()

    class Meta:
        table_name = "task_locks"


class TaskDependencyModel(Model):
    task_id = CharField()
    depends_on_task_id = CharField()

    class Meta:
        table_name = "task_dependencies"
        primary_key = CompositeKey("task_id", "depends_on_task_id")


class TaskEventModel(Model):
    id = CharField(primary_key=True)
    task_id = CharField()
    event_type = CharField()
    actor = CharField()
    payload = TextField(default="{}")
    created_at = DateTimeField()

    class Meta:
        table_name = "task_events"


ALL_MODELS: list[type[Model]] = [TaskModel, TaskLockModel, TaskDependencyModel, TaskEventModel]


def init_task_database(db_path: str) -> None:
    database.init(db_path)
    database.bind(ALL_MODELS)
