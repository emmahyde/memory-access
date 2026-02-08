from enum import Enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Frame(str, Enum):
    """Canonical semantic frames for normalizing insights."""

    CAUSAL = "causal"
    CONSTRAINT = "constraint"
    PATTERN = "pattern"
    EQUIVALENCE = "equivalence"
    TAXONOMY = "taxonomy"
    PROCEDURE = "procedure"


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
