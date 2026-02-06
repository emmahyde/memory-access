from semantic_memory.models import Frame, Insight, SearchResult


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
