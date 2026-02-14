"""Type stubs for orm_models.

Peewee's metaclass replaces Field attributes with FieldAccessor descriptors
that return Python types on instance access but Field objects on class access
(for query building). These stubs use overloaded descriptors to model both.
"""

from datetime import datetime
from typing import Generic, TypeVar, overload

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

_T = TypeVar("_T")
_F = TypeVar("_F")

class _Descriptor(Generic[_T, _F]):
    """Models peewee's FieldAccessor: returns Field on class access, Python type on instance."""
    @overload
    def __get__(self, obj: None, objtype: type) -> _F: ...
    @overload
    def __get__(self, obj: Model, objtype: type) -> _T: ...

database: SqliteDatabase

class TaskModel(Model):
    task_id: _Descriptor[str, CharField]
    title: _Descriptor[str, TextField]
    status: _Descriptor[str, CharField]
    owner: _Descriptor[str, CharField]
    retry_count: _Descriptor[int, IntegerField]
    version: _Descriptor[int, IntegerField]
    created_at: _Descriptor[datetime, DateTimeField]
    updated_at: _Descriptor[datetime, DateTimeField]
    class Meta:
        table_name: str

class TaskLockModel(Model):
    id: _Descriptor[str, CharField]
    task_id: _Descriptor[str, CharField]
    resource: _Descriptor[str, TextField]
    active: _Descriptor[bool, BooleanField]
    created_at: _Descriptor[datetime, DateTimeField]
    class Meta:
        table_name: str

class TaskDependencyModel(Model):
    task_id: _Descriptor[str, CharField]
    depends_on_task_id: _Descriptor[str, CharField]
    class Meta:
        table_name: str

class TaskEventModel(Model):
    id: _Descriptor[str, CharField]
    task_id: _Descriptor[str, CharField]
    event_type: _Descriptor[str, CharField]
    actor: _Descriptor[str, CharField]
    payload: _Descriptor[str, TextField]
    created_at: _Descriptor[datetime, DateTimeField]
    class Meta:
        table_name: str

ALL_MODELS: list[type[Model]]

def init_task_database(db_path: str) -> None: ...
