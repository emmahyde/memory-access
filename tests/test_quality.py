from memory_access.models import Frame, Insight
from memory_access.normalizer import compute_confidence


class TestComputeConfidence:
    def test_high_confidence_causal_with_entities(self):
        insight = Insight(
            text="original",
            normalized_text="Race condition in Redis pub/sub causes message loss because subscriber reconnects drop buffered messages",
            frame=Frame.CAUSAL,
            entities=["Redis", "pub/sub"],
            problems=["race condition", "message loss"],
        )
        score = compute_confidence(insight)
        assert score > 0.7

    def test_low_confidence_short_generic_taxonomy(self):
        insight = Insight(
            text="original",
            normalized_text="Lighting is a type of component",
            frame=Frame.TAXONOMY,
            entities=["lighting"],
        )
        score = compute_confidence(insight)
        assert score < 0.5

    def test_low_confidence_very_short(self):
        insight = Insight(
            text="original",
            normalized_text="X is Y",
            frame=Frame.EQUIVALENCE,
        )
        score = compute_confidence(insight)
        assert score < 0.3

    def test_medium_confidence_single_entity(self):
        insight = Insight(
            text="original",
            normalized_text="Python requires virtual environments for dependency isolation",
            frame=Frame.CONSTRAINT,
            entities=["Python"],
        )
        score = compute_confidence(insight)
        assert 0.5 <= score <= 0.9

    def test_generic_has_pattern_penalized(self):
        insight = Insight(
            text="original",
            normalized_text="The system has multiple components for processing",
            frame=Frame.TAXONOMY,
            entities=["system"],
        )
        score = compute_confidence(insight)
        assert score < 0.5

    def test_procedure_with_multiple_entities(self):
        insight = Insight(
            text="original",
            normalized_text="To deploy to production, run: docker build, then docker push, then kubectl apply",
            frame=Frame.PROCEDURE,
            entities=["docker", "kubectl"],
            contexts=["production"],
        )
        score = compute_confidence(insight)
        assert score > 0.6

    def test_score_always_between_0_and_1(self):
        for frame in Frame:
            insight = Insight(
                text="t",
                normalized_text="A" * 100,
                frame=frame,
                entities=["a", "b", "c"],
                problems=["p"],
                resolutions=["r"],
            )
            score = compute_confidence(insight)
            assert 0.0 <= score <= 1.0

    def test_empty_entities_penalized(self):
        insight = Insight(
            text="original",
            normalized_text="Something happens when conditions are met in the system",
            frame=Frame.CAUSAL,
        )
        score = compute_confidence(insight)
        # No entities/problems/resolutions -> 0.4 multiplier
        assert score < 0.5
