from __future__ import annotations

import os

import anthropic
from mcp.server.fastmcp import FastMCP

from .embeddings import EmbeddingEngine, BedrockEmbeddingEngine, create_embedding_engine
from .normalizer import Normalizer
from .storage import InsightStore


class SemMemApp:
    """Application wrapper holding shared state for MCP tool handlers."""

    def __init__(self, store: InsightStore, embeddings: EmbeddingEngine | BedrockEmbeddingEngine, normalizer: Normalizer):
        self.store = store
        self.embeddings = embeddings
        self.normalizer = normalizer

    async def store_insight(
        self,
        text: str,
        domain: str = "",
        source: str = "",
        repo: str = "",
        pr: str = "",
        author: str = "",
        project: str = "",
        task: str = "",
    ) -> str:
        domains = [d.strip() for d in domain.split(",") if d.strip()] if domain else []
        insights = await self.normalizer.normalize(text, source=source, domains=domains)
        if not insights:
            return "No insights extracted from text."
        texts_to_embed = [i.normalized_text for i in insights]
        embeddings = self.embeddings.embed_batch(texts_to_embed)
        ids = []
        for insight, emb in zip(insights, embeddings):
            insight_id = await self.store.insert(
                insight, emb, repo=repo, pr=pr, author=author, project=project, task=task
            )
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

    async def search_by_subject(self, name: str, kind: str = "", limit: int = 20) -> str:
        results = await self.store.search_by_subject(
            name=name, kind=kind or None, limit=limit
        )
        if not results:
            return "No insights found for that subject."
        lines = []
        for i in results:
            short_id = (i.id or "unknown")[:8]
            lines.append(f"[{short_id}] ({i.frame.value}) {i.normalized_text}")
            if i.domains:
                lines.append(f"  Domains: {', '.join(i.domains)}")
        return "\n".join(lines)

    async def related_insights(self, insight_id: str, limit: int = 10) -> str:
        results = await self.store.related_insights(insight_id, limit=limit)
        if not results:
            return "No related insights found."
        lines = [f"- [{r.insight.id}] (score={r.score:.3f}) {r.insight.normalized_text}" for r in results]
        return f"Found {len(results)} related insight(s):\n" + "\n".join(lines)

    async def add_subject_relation(
        self, from_name: str, from_kind: str, to_name: str, to_kind: str, relation_type: str
    ) -> str:
        success = await self.store.add_subject_relation(
            from_name=from_name,
            from_kind=from_kind,
            to_name=to_name,
            to_kind=to_kind,
            relation_type=relation_type,
        )
        if success:
            return f"Created relation: ({from_name}:{from_kind}) --[{relation_type}]--> ({to_name}:{to_kind})"
        return "Failed to create relation."

    async def get_subject_relations(
        self, name: str, kind: str = "", relation_type: str = "", limit: int = 50
    ) -> str:
        results = await self.store.get_subject_relations(
            name=name,
            kind=kind or None,
            relation_type=relation_type or None,
            limit=limit,
        )
        if not results:
            return "No relations found for that subject."
        lines = []
        for rel in results:
            lines.append(
                f"({rel['from_name']}:{rel['from_kind']}) --[{rel['relation_type']}]--> ({rel['to_name']}:{rel['to_kind']})"
            )
        return f"Found {len(results)} relation(s):\n" + "\n".join(lines)

    async def search_knowledge_base(self, query: str, kb_name: str = "", limit: int = 5) -> str:
        """Search KB chunks by semantic similarity."""
        query_emb = self.embeddings.embed(query)
        kb_id = None
        if kb_name:
            kb = await self.store.get_kb_by_name(kb_name)
            if kb is None:
                return f"Knowledge base '{kb_name}' not found."
            kb_id = kb.id
        results = await self.store.search_kb_by_embedding(query_emb, kb_id=kb_id, limit=limit)
        if not results:
            return "No matching content found in knowledge bases."
        lines = []
        for r in results:
            lines.append(f"[{r.score:.3f}] ({r.insight.frame.value}) {r.insight.normalized_text}")
            if r.insight.text != r.insight.normalized_text:
                lines.append(f"  Original: {r.insight.text}")
            if r.insight.source:
                lines.append(f"  Source: {r.insight.source}")
        return "\n".join(lines)

    async def list_knowledge_bases(self) -> str:
        """List all knowledge bases."""
        kbs = await self.store.list_kbs()
        if not kbs:
            return "No knowledge bases found."
        lines = []
        for kb in kbs:
            lines.append(f"- {kb.name}: {kb.description or '(no description)'} [{kb.source_type or 'unknown'}]")
        return "\n".join(lines)


async def create_app(
    db_path: str | None = None,
    embedding_model: str = "text-embedding-3-small",
    anthropic_client: anthropic.Anthropic | None = None,
    embedding_provider: str | None = None,
    llm_provider: str | None = None,
    embeddings: EmbeddingEngine | BedrockEmbeddingEngine | None = None,
) -> SemMemApp:
    db_path = db_path or os.environ.get(
        "MEMORY_DB_PATH",
        os.path.expanduser("~/.claude/sem-mem/memory.db"),
    )
    store = InsightStore(db_path)
    await store.initialize()
    embedding_provider = embedding_provider or os.environ.get("EMBEDDING_PROVIDER", "openai")
    llm_provider = llm_provider or os.environ.get("LLM_PROVIDER", "anthropic")
    if embeddings is None:
        embeddings = create_embedding_engine(provider=embedding_provider, model=embedding_model)
    normalizer = Normalizer(client=anthropic_client, provider=llm_provider)
    return SemMemApp(store=store, embeddings=embeddings, normalizer=normalizer)


def create_mcp_server() -> FastMCP:
    mcp = FastMCP("sem-mem")
    app: SemMemApp | None = None

    @mcp.tool()
    async def store_insight(
        text: str,
        domain: str = "",
        source: str = "",
        repo: str = "",
        pr: str = "",
        author: str = "",
        project: str = "",
        task: str = "",
    ) -> str:
        """Store a new insight. Text is decomposed into atomic insights, normalized into canonical semantic frames, embedded, and stored for intent-based retrieval. Optional git context (repo, pr, author, project, task) creates subjects and relations in the knowledge graph."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.store_insight(
            text=text, domain=domain, source=source, repo=repo, pr=pr, author=author, project=project, task=task
        )

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

    @mcp.tool()
    async def search_by_subject(name: str, kind: str = "", limit: int = 20) -> str:
        """Search for insights by subject name (domain, entity, or other subject kind). Returns insights tagged with that subject."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.search_by_subject(name=name, kind=kind, limit=limit)

    @mcp.tool()
    async def related_insights(insight_id: str, limit: int = 10) -> str:
        """Find insights related to a given insight via shared subjects. Returns insights connected through common domains, entities, problems, resolutions, or contexts."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.related_insights(insight_id=insight_id, limit=limit)

    @mcp.tool()
    async def add_subject_relation(
        from_name: str, from_kind: str, to_name: str, to_kind: str, relation_type: str
    ) -> str:
        """Create a typed relation between two subjects in the knowledge graph. Valid relation types include: contains, scopes, frames, solved_by, implemented_in, applies_to, involves, has_problem, addresses, produces, works_on, authors, resolves."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.add_subject_relation(
            from_name=from_name,
            from_kind=from_kind,
            to_name=to_name,
            to_kind=to_kind,
            relation_type=relation_type,
        )

    @mcp.tool()
    async def get_subject_relations(
        name: str, kind: str = "", relation_type: str = "", limit: int = 50
    ) -> str:
        """Get relations from a subject in the knowledge graph. Returns typed edges connecting this subject to others."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.get_subject_relations(
            name=name, kind=kind, relation_type=relation_type, limit=limit
        )

    @mcp.tool()
    async def search_knowledge_base(query: str, kb_name: str = "", limit: int = 5) -> str:
        """Search for relevant content in knowledge bases by semantic similarity.
        Searches within a specific knowledge base if kb_name is provided,
        or across all knowledge bases if omitted."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.search_knowledge_base(query=query, kb_name=kb_name, limit=limit)

    @mcp.tool()
    async def list_knowledge_bases() -> str:
        """List all available knowledge bases with their descriptions and chunk counts."""
        nonlocal app
        if app is None:
            app = await create_app()
        return await app.list_knowledge_bases()

    return mcp


def main():
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
