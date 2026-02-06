import os
from pathlib import Path

import anthropic
from mcp.server.fastmcp import FastMCP

from .embeddings import EmbeddingEngine
from .models import Insight
from .normalizer import Normalizer
from .storage import InsightStore


class SemanticMemoryApp:
    """Application wrapper holding shared state for MCP tool handlers."""

    def __init__(self, store: InsightStore, embeddings: EmbeddingEngine, normalizer: Normalizer):
        self.store = store
        self.embeddings = embeddings
        self.normalizer = normalizer

    async def store_insight(self, text: str, domain: str = "", source: str = "") -> str:
        domains = [d.strip() for d in domain.split(",") if d.strip()] if domain else []
        insights = await self.normalizer.normalize(text, source=source, domains=domains)
        ids = []
        for insight in insights:
            emb = self.embeddings.embed(insight.normalized_text)
            insight_id = await self.store.insert(insight, emb)
            ids.append(insight_id)
        return f"Stored {len(ids)} insight(s): {', '.join(ids)}"

    async def search_insights(self, query: str, domain: str = "", limit: int = 5) -> str:
        query_emb = self.embeddings.embed(query)
        results = await self.store.search_by_embedding(
            query_emb, limit=limit, domain=domain or None
        )
        if not results:
            return "No matching insights found."
        lines = []
        for r in results:
            lines.append(f"[{r.score:.3f}] ({r.insight.frame.value}) {r.insight.normalized_text}")
            if r.insight.text != r.insight.normalized_text:
                lines.append(f"  Original: {r.insight.text}")
            if r.insight.domains:
                lines.append(f"  Domains: {', '.join(r.insight.domains)}")
        return "\n".join(lines)

    async def update_insight(self, insight_id: str, confidence: float | None = None) -> str:
        kwargs = {}
        if confidence is not None:
            kwargs["confidence"] = confidence
        updated = await self.store.update(insight_id, **kwargs)
        if updated is None:
            return f"Insight {insight_id} not found."
        return f"Updated insight {insight_id}."

    async def forget(self, insight_id: str) -> str:
        deleted = await self.store.delete(insight_id)
        if not deleted:
            return f"Insight {insight_id} not found."
        return f"Forgot insight {insight_id}."

    async def list_insights(self, domain: str = "", frame: str = "", limit: int = 20) -> str:
        results = await self.store.list_all(
            domain=domain or None, frame=frame or None, limit=limit
        )
        if not results:
            return "No insights stored."
        lines = []
        for i in results:
            short_id = (i.id or "unknown")[:8]
            lines.append(f"[{short_id}] ({i.frame.value}) {i.normalized_text}")
            if i.domains:
                lines.append(f"  Domains: {', '.join(i.domains)}")
        return "\n".join(lines)


async def create_app(
    db_path: str | None = None,
    embedding_model: str = "text-embedding-3-small",
    anthropic_client: anthropic.Anthropic | None = None,
) -> SemanticMemoryApp:
    db_path = db_path or os.environ.get(
        "MEMORY_DB_PATH",
        os.path.expanduser("~/.claude/semantic-memory/memory.db"),
    )
    store = InsightStore(db_path)
    await store.initialize()
    embeddings = EmbeddingEngine(embedding_model)
    normalizer = Normalizer(client=anthropic_client)
    return SemanticMemoryApp(store=store, embeddings=embeddings, normalizer=normalizer)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("semantic-memory")
    app: SemanticMemoryApp | None = None

    @mcp.tool()
    async def store_insight(text: str, domain: str = "", source: str = "") -> str:
        """Store a new insight. Text is decomposed into atomic insights, normalized into canonical semantic frames, embedded, and stored for intent-based retrieval."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.store_insight(text=text, domain=domain, source=source)

    @mcp.tool()
    async def search_insights(query: str, domain: str = "", limit: int = 5) -> str:
        """Search for insights by semantic similarity. Returns ranked results matching the intent of the query."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.search_insights(query=query, domain=domain, limit=limit)

    @mcp.tool()
    async def update_insight(insight_id: str, confidence: float = 1.0) -> str:
        """Update an existing insight's confidence score."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.update_insight(insight_id=insight_id, confidence=confidence)

    @mcp.tool()
    async def forget(insight_id: str) -> str:
        """Remove an insight from memory."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.forget(insight_id=insight_id)

    @mcp.tool()
    async def list_insights(domain: str = "", frame: str = "", limit: int = 20) -> str:
        """List stored insights, optionally filtered by domain or semantic frame type."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.list_insights(domain=domain, frame=frame, limit=limit)

    return mcp


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
