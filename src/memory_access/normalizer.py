import asyncio
import json
import logging
import os
import re

import anthropic
from anthropic.types import TextBlock

from .models import Frame, Insight

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT = """\
Decompose the following text into insights. Each insight should express a meaningful \
concept, relationship, or principle that is specific and actionable.

Rules:
- Keep related context together (e.g., "X causes Y in context Z" is ONE insight, not three)
- Skip generic definitions that lack specificity (e.g., "X is a type of Y" where both are obvious)
- Prefer insights that explain WHY or HOW over what things ARE
- Aim for 1-5 insights per input, not exhaustive enumeration

Text: {text}

Return a JSON array of strings, each being one insight. \
If the text contains no meaningful insights, return an empty array [].
Return ONLY valid JSON, no explanation."""

CLASSIFY_PROMPT = """\
Classify this insight into exactly one semantic frame and rewrite it in a clear, specific form.

Insight: {text}

Frames and templates:
- causal: "{{condition}} causes {{effect}}" or "{{condition}} causes {{effect}} because {{mechanism}}"
- constraint: "{{action}} requires {{precondition}}"
- pattern: "When {{situation}}, prefer {{approach}} over {{alternative}} because {{reason}}"
- equivalence: "{{A}} is equivalent to {{B}} in context {{C}}"
- taxonomy: "{{specific}} is a type of {{general}} with property {{distinguishing_property}}"
- procedure: "To achieve {{goal}}, do: {{step1}}, then {{step2}}, ..."

Rewriting rules:
- Preserve technical terms exactly (variable names, library names, error codes)
- Make implicit causality explicit (add "because" if reasoning is implied)
- Include context if mentioned in original (e.g., "in production", "during initialization")
- Keep normalized text under 200 characters by removing filler words

Return JSON: {{"frame": "<frame>", "normalized": "<rewritten text>", "entities": ["<entity1>", ...], "problems": ["<problem1>", ...], "resolutions": ["<resolution1>", ...], "contexts": ["<context1>", ...]}}

Rules for extraction:
- entities: technical things mentioned (tools, libraries, protocols, concepts, code constructs)
- problems: issues, bugs, failures, or pain points described (empty array if none)
- resolutions: fixes, solutions, or workarounds described (empty array if none)
- contexts: situational qualifiers like "production", "CI pipeline", "React 18+" (empty array if none)

Return ONLY valid JSON, no explanation."""


def _parse_json(text: str):
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return json.loads(text)


def compute_confidence(insight) -> float:
    """Compute confidence score based on heuristics.

    Returns 0.0-1.0 where:
    - 0.0-0.3: Low-information noise (filter at ingest)
    - 0.3-0.6: Marginal quality (borderline)
    - 0.6-1.0: High-value insight (keep)
    """
    score = 1.0

    # Length heuristic: very short insights are likely generic
    if len(insight.normalized_text) < 20:
        score *= 0.3
    elif len(insight.normalized_text) < 40:
        score *= 0.7

    # Generic phrase detection
    generic_patterns = [
        r"^.+ is a (type of|kind of|form of) .+$",
        r"^.+ (can be|may be) .+$",
        r"^.+ (has|have) .+$",
    ]
    for pattern in generic_patterns:
        if re.match(pattern, insight.normalized_text, re.IGNORECASE):
            score *= 0.5
            break

    # Information density: count extracted subjects
    info_count = len(insight.entities) + len(insight.problems) + len(insight.resolutions)
    if info_count == 0:
        score *= 0.4
    elif info_count == 1:
        score *= 0.7

    # Frame quality: some frames are inherently more valuable
    frame_weights = {
        Frame.CAUSAL: 1.0,
        Frame.CONSTRAINT: 1.0,
        Frame.PATTERN: 1.0,
        Frame.PROCEDURE: 0.9,
        Frame.TAXONOMY: 0.6,
        Frame.EQUIVALENCE: 0.8,
    }
    score *= frame_weights.get(insight.frame, 1.0)

    return max(0.0, min(1.0, score))


class Normalizer:
    """Decomposes and classifies text into canonical semantic frames using an LLM."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
        if client:
            self.client = client
        elif provider == "bedrock":
            self.client = anthropic.AnthropicBedrock(
                aws_region=os.environ.get("AWS_REGION", "us-east-1"),
                aws_profile=os.environ.get("AWS_PROFILE"),
            )
        else:
            self.client = anthropic.Anthropic()
        if model:
            self.model = model
        elif provider == "bedrock":
            self.model = os.environ.get(
                "BEDROCK_LLM_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
            )
        else:
            self.model = "claude-haiku-4-5-20251001"

    async def decompose(self, text: str) -> list[str]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(text=text)}],
        )
        block = response.content[0]
        assert isinstance(block, TextBlock)
        return _parse_json(block.text)

    async def classify(self, text: str) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(text=text)}],
        )
        block = response.content[0]
        assert isinstance(block, TextBlock)
        return _parse_json(block.text)

    async def normalize(
        self, text: str, source: str = "", domains: list[str] | None = None
    ) -> list[Insight]:
        atoms = await self.decompose(text)
        classifications = await asyncio.gather(*[self.classify(atom) for atom in atoms])

        insights = []
        for atom, classification in zip(atoms, classifications):
            insight = Insight(
                text=atom,
                normalized_text=classification["normalized"],
                frame=Frame(classification["frame"]),
                entities=classification.get("entities", []),
                problems=classification.get("problems", []),
                resolutions=classification.get("resolutions", []),
                contexts=classification.get("contexts", []),
                domains=domains or [],
                source=source,
            )
            insight.confidence = compute_confidence(insight)
            insights.append(insight)
        return insights
