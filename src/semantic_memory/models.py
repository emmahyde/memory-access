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
    confidence: float = 1.0
    source: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SearchResult(BaseModel):
    """An insight with its similarity score from a search query."""

    insight: Insight
    score: float
