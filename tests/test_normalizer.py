import json
import pytest
from unittest.mock import MagicMock, patch
from anthropic.types import TextBlock
from memory_access.normalizer import Normalizer
from memory_access.models import Frame


def _mock_anthropic_response(text: str):
    """Create a mock Anthropic API response."""
    mock_response = MagicMock()
    # Create a real TextBlock instead of a generic MagicMock
    text_block = TextBlock(type="text", text=text)
    mock_response.content = [text_block]
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
                "problems": [],
                "resolutions": [],
                "contexts": [],
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
                "problems": [],
                "resolutions": [],
                "contexts": [],
            })
        )
        normalizer = Normalizer(client=mock_client)
        result = await normalizer.classify("JWT decoding requires non-null token input")
        assert result["frame"] == "constraint"

    async def test_classifies_with_problem_and_resolution(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps({
                "frame": "causal",
                "normalized": "Memory leak in connection pool causes OOM",
                "entities": ["connection pool"],
                "problems": ["memory leak", "OOM"],
                "resolutions": [],
                "contexts": ["production"],
            })
        )
        normalizer = Normalizer(client=mock_client)
        result = await normalizer.classify("Memory leak in production connection pool causing OOM")
        assert result["problems"] == ["memory leak", "OOM"]
        assert result["contexts"] == ["production"]


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
                "problems": ["null pointer"],
                "resolutions": ["null checks"],
                "contexts": [],
            })),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "Middleware ordering causes auth failures",
                "entities": ["middleware", "auth"],
                "problems": ["auth failures"],
                "resolutions": [],
                "contexts": ["production"],
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
        assert insights[0].problems == ["null pointer"]
        assert insights[0].resolutions == ["null checks"]
        assert insights[1].frame == Frame.CAUSAL
        assert insights[1].problems == ["auth failures"]
        assert insights[1].contexts == ["production"]


class TestBedrockNormalizer:
    def test_bedrock_provider_creates_bedrock_client(self):
        with patch("memory_access.normalizer.anthropic") as mock_anthropic:
            mock_bedrock_client = MagicMock()
            mock_anthropic.AnthropicBedrock.return_value = mock_bedrock_client
            normalizer = Normalizer(provider="bedrock")
            assert normalizer.client is mock_bedrock_client
            mock_anthropic.AnthropicBedrock.assert_called_once()

    def test_bedrock_default_model(self):
        with patch("memory_access.normalizer.anthropic") as mock_anthropic:
            normalizer = Normalizer(provider="bedrock")
            assert normalizer.model == "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_bedrock_custom_model_from_env(self):
        with patch("memory_access.normalizer.anthropic") as mock_anthropic:
            with patch.dict("os.environ", {"BEDROCK_LLM_MODEL": "custom-model"}):
                normalizer = Normalizer(provider="bedrock")
                assert normalizer.model == "custom-model"

    def test_bedrock_region_from_env(self):
        with patch("memory_access.normalizer.anthropic") as mock_anthropic:
            with patch.dict("os.environ", {"AWS_REGION": "eu-west-1", "AWS_PROFILE": "myprofile"}):
                normalizer = Normalizer(provider="bedrock")
                mock_anthropic.AnthropicBedrock.assert_called_once_with(
                    aws_region="eu-west-1",
                    aws_profile="myprofile",
                )

    def test_explicit_client_overrides_provider(self):
        explicit_client = MagicMock()
        normalizer = Normalizer(client=explicit_client, provider="bedrock")
        assert normalizer.client is explicit_client

    async def test_bedrock_decompose_works(self):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            json.dumps(["Bedrock insight"])
        )
        normalizer = Normalizer(client=mock_client, provider="bedrock")
        atoms = await normalizer.decompose("Bedrock insight")
        assert atoms == ["Bedrock insight"]

    def test_default_provider_creates_anthropic_client(self):
        with patch("memory_access.normalizer.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.Anthropic.return_value = mock_client
            normalizer = Normalizer()
            assert normalizer.client is mock_client
            assert normalizer.model == "claude-haiku-4-5-20251001"
