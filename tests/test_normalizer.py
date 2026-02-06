import json
import pytest
from unittest.mock import MagicMock, patch
from semantic_memory.normalizer import Normalizer
from semantic_memory.models import Frame


def _mock_anthropic_response(text: str):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


class TestDecompose:
    async def test_decomposes_compound_text(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps([
                "JWT decoder requires null-safety guards",
                "Session middleware ordering affects auth flow",
            ])
        )
        normalizer = Normalizer(client=mock_client)
        atoms = await normalizer.decompose(
            "I fixed the auth bug by adding null checks to the JWT decoder "
            "and also discovered that the session middleware was running in the wrong order"
        )
        assert len(atoms) == 2
        assert "JWT" in atoms[0]
        assert "middleware" in atoms[1]

    async def test_atomic_text_returns_single_element(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(["React re-renders when state changes"])
        )
        normalizer = Normalizer(client=mock_client)
        atoms = await normalizer.decompose("React re-renders when state changes")
        assert len(atoms) == 1


class TestClassify:
    async def test_classifies_causal_insight(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps({
                "frame": "causal",
                "normalized": "State mutation causes React to skip re-renders",
                "entities": ["React", "state mutation"],
            })
        )
        normalizer = Normalizer(client=mock_client)
        result = await normalizer.classify("Mutating state directly causes React to skip re-renders")
        assert result["frame"] == "causal"
        assert "entities" in result
        assert isinstance(result["entities"], list)

    async def test_classifies_constraint_insight(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps({
                "frame": "constraint",
                "normalized": "JWT decoding requires non-null token input",
                "entities": ["JWT", "token"],
            })
        )
        normalizer = Normalizer(client=mock_client)
        result = await normalizer.classify("JWT decoding requires non-null token input")
        assert result["frame"] == "constraint"


class TestNormalizePipeline:
    async def test_full_normalize_produces_insights(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps([
                "JWT decoding requires null checks",
                "Middleware ordering affects auth",
            ])),
            _mock_anthropic_response(json.dumps({
                "frame": "constraint",
                "normalized": "JWT decoding requires non-null token input",
                "entities": ["JWT"],
            })),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "Middleware ordering causes auth failures",
                "entities": ["middleware", "auth"],
            })),
        ]
        normalizer = Normalizer(client=mock_client)
        insights = await normalizer.normalize(
            "Fixed auth by adding null checks to JWT and reordering middleware",
            source="debug",
            domains=["node", "auth"],
        )
        assert len(insights) == 2
        assert insights[0].frame == Frame.CONSTRAINT
        assert insights[0].source == "debug"
        assert insights[0].domains == ["node", "auth"]
        assert insights[1].frame == Frame.CAUSAL
