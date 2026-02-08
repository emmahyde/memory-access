from sem_mem.models import Frame, Insight, SearchResult, KnowledgeBase, KbChunk, CrawledPage


class TestFrame:
    def test_all_six_frames_exist(self):
        assert len(Frame) == 6
        assert Frame.CAUSAL == "causal"
        assert Frame.CONSTRAINT == "constraint"
        assert Frame.PATTERN == "pattern"
        assert Frame.EQUIVALENCE == "equivalence"
        assert Frame.TAXONOMY == "taxonomy"
        assert Frame.PROCEDURE == "procedure"


class TestInsight:
    def test_create_minimal_insight(self):
        insight = Insight(text="React re-renders on state change")
        assert insight.text == "React re-renders on state change"
        assert insight.normalized_text == ""
        assert insight.frame == Frame.CAUSAL
        assert insight.domains == []
        assert insight.entities == []
        assert insight.confidence == 1.0
        assert insight.source == ""
        assert insight.id is None

    def test_create_full_insight(self):
        insight = Insight(
            id="abc-123",
            text="Mutating state directly causes React to skip re-renders",
            normalized_text="Mutating state directly causes React to skip re-renders",
            frame=Frame.CAUSAL,
            domains=["react", "frontend"],
            entities=["React", "state mutation"],
            confidence=0.95,
            source="debugging_session",
        )
        assert insight.id == "abc-123"
        assert insight.frame == Frame.CAUSAL
        assert insight.domains == ["react", "frontend"]
        assert insight.confidence == 0.95

    def test_insight_serialization_roundtrip(self):
        insight = Insight(
            text="test",
            normalized_text="normalized",
            frame=Frame.PATTERN,
            domains=["python"],
        )
        data = insight.model_dump()
        restored = Insight(**data)
        assert restored == insight


class TestSearchResult:
    def test_search_result(self):
        insight = Insight(text="test", frame=Frame.CAUSAL)
        result = SearchResult(insight=insight, score=0.87)
        assert result.score == 0.87
        assert result.insight.text == "test"


class TestKnowledgeBase:
    def test_create_minimal_kb(self):
        kb = KnowledgeBase(name="rails-docs")
        assert kb.name == "rails-docs"
        assert kb.description == ""
        assert kb.source_type == ""
        assert kb.id is None
        assert kb.created_at is None

    def test_create_full_kb(self):
        kb = KnowledgeBase(
            id="kb-123",
            name="rails-docs",
            description="Ruby on Rails documentation",
            source_type="crawl",
        )
        assert kb.id == "kb-123"
        assert kb.source_type == "crawl"

    def test_kb_serialization_roundtrip(self):
        kb = KnowledgeBase(name="test-kb", description="test", source_type="scrape")
        data = kb.model_dump()
        restored = KnowledgeBase(**data)
        assert restored == kb


class TestKbChunk:
    def test_create_minimal_chunk(self):
        chunk = KbChunk(kb_id="kb-1", text="some text")
        assert chunk.kb_id == "kb-1"
        assert chunk.text == "some text"
        assert chunk.normalized_text == ""
        assert chunk.frame == Frame.CAUSAL
        assert chunk.domains == []
        assert chunk.entities == []
        assert chunk.problems == []
        assert chunk.resolutions == []
        assert chunk.contexts == []
        assert chunk.confidence == 1.0
        assert chunk.source_url == ""

    def test_create_full_chunk(self):
        chunk = KbChunk(
            id="chunk-1",
            kb_id="kb-1",
            text="original",
            normalized_text="State change causes re-render",
            frame=Frame.CAUSAL,
            domains=["react"],
            entities=["React"],
            problems=["stale state"],
            resolutions=["use useEffect"],
            contexts=["frontend"],
            confidence=0.95,
            source_url="https://reactjs.org/docs",
        )
        assert chunk.id == "chunk-1"
        assert chunk.confidence == 0.95
        assert chunk.source_url == "https://reactjs.org/docs"

    def test_chunk_mirrors_insight_fields(self):
        """KbChunk should have the same semantic fields as Insight minus git context."""
        chunk_fields = set(KbChunk.model_fields.keys())
        insight_fields = set(Insight.model_fields.keys())
        # KbChunk has kb_id and source_url instead of source
        shared = {"text", "normalized_text", "frame", "domains", "entities",
                  "problems", "resolutions", "contexts", "confidence",
                  "created_at", "updated_at", "id"}
        assert shared.issubset(chunk_fields)
        assert shared.issubset(insight_fields)

    def test_chunk_serialization_roundtrip(self):
        chunk = KbChunk(kb_id="kb-1", text="test", domains=["python"])
        data = chunk.model_dump()
        restored = KbChunk(**data)
        assert restored == chunk


class TestCrawledPage:
    def test_create_minimal_page(self):
        page = CrawledPage(url="https://example.com", markdown="# Hello")
        assert page.url == "https://example.com"
        assert page.markdown == "# Hello"
        assert page.metadata == {}

    def test_create_page_with_metadata(self):
        page = CrawledPage(
            url="https://example.com/page",
            markdown="# Content",
            metadata={"title": "Example", "statusCode": 200},
        )
        assert page.metadata["title"] == "Example"
        assert page.metadata["statusCode"] == 200

    def test_page_serialization_roundtrip(self):
        page = CrawledPage(url="https://example.com", markdown="text", metadata={"key": "val"})
        data = page.model_dump()
        restored = CrawledPage(**data)
        assert restored == page
