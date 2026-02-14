from enum import Enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Frame(str, Enum):
    """Canonical semantic frames for normalizing insights."""

    CAUSAL = "causal"
    CONSTRAINT = "constraint"
    PATTERN = "pattern"
    EQUIVALENCE = "equivalence"
    TAXONOMY = "taxonomy"
    PROCEDURE = "procedure"


class TaskState(str, Enum):
    """Task lifecycle states for orchestrated multi-agent execution."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class Insight(BaseModel):
    """A single atomic insight stored in semantic memory."""

    id: Optional[str] = None
    text: str
    normalized_text: str = ""
    frame: Frame = Frame.CAUSAL
    domains: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GitContext(BaseModel):
    """Optional git metadata to associate with insights."""

    repo: str = ""
    pr: str = ""
    author: str = ""
    project: str = ""
    task: str = ""


class SearchResult(BaseModel):
    """An insight with its similarity score from a search query."""

    insight: Insight
    score: float


class KnowledgeBase(BaseModel):
    """A collection of document chunks from an external source."""
    id: Optional[str] = None
    name: str
    description: str = ""
    source_type: str = ""  # 'crawl', 'scrape', 'file', 'text'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KbChunk(BaseModel):
    """A normalized chunk from a knowledge base document."""
    id: Optional[str] = None
    kb_id: str
    text: str
    normalized_text: str = ""
    frame: Frame = Frame.CAUSAL
    domains: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source_url: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CrawledPage(BaseModel):
    """A single page returned by a crawl service."""
    url: str
    markdown: str
    metadata: dict = Field(default_factory=dict)


class TaskRecord(BaseModel):
    """Persistent task row."""

    task_id: str
    title: str
    status: TaskState
    owner: str = ""
    retry_count: int = 0
    version: int = 0
    created_at: datetime
    updated_at: datetime


class TaskLockRecord(BaseModel):
    """Active or historical lock held by a task."""

    id: str
    task_id: str
    resource: str
    active: bool
    created_at: datetime


class TaskDependencyRecord(BaseModel):
    """Dependency edge from a task to another task."""

    task_id: str
    depends_on_task_id: str


class TaskEventRecord(BaseModel):
    """Append-only task audit log entry."""

    id: str
    task_id: str
    event_type: str
    actor: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TransitionRequest(BaseModel):
    """Transition request with optimistic concurrency guard."""

    task_id: str
    from_state: TaskState
    to_state: TaskState
    actor: str
    reason: str = ""
    evidence: str = ""
    expected_version: int


class TransitionResult(BaseModel):
    """Result for a state transition attempt."""

    task: TaskRecord
    event_id: str
