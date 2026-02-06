import json

import anthropic

from .models import Frame, Insight

DECOMPOSE_PROMPT = """\
Decompose the following text into atomic insights. Each insight should express \
exactly one concept, relationship, or principle.

Text: {text}

Return a JSON array of strings, each being one atomic insight. \
If the text is already atomic, return a single-element array.
Return ONLY valid JSON, no explanation."""

CLASSIFY_PROMPT = """\
Classify this insight into exactly one semantic frame and rewrite it in canonical form.

Insight: {text}

Frames and templates:
- causal: "{{condition}} causes {{effect}}"
- constraint: "{{action}} requires {{precondition}}"
- pattern: "When {{situation}}, prefer {{approach}} over {{alternative}}"
- equivalence: "{{A}} is equivalent to {{B}} in context {{C}}"
- taxonomy: "{{specific}} is a type of {{general}}"
- procedure: "To achieve {{goal}}, do {{steps}} in order"

Return JSON: {{"frame": "<frame>", "normalized": "<canonical text>", "entities": ["<entity1>", ...], "problems": ["<problem1>", ...], "resolutions": ["<resolution1>", ...], "contexts": ["<context1>", ...]}}

Rules for extraction:
- entities: technical things mentioned (tools, libraries, protocols, concepts)
- problems: issues, bugs, failures, or pain points described (empty array if none)
- resolutions: fixes, solutions, or workarounds described (empty array if none)
- contexts: situational context like "production", "CI pipeline", "code review" (empty array if none)
Return ONLY valid JSON, no explanation."""


class Normalizer:
    """Decomposes and classifies text into canonical semantic frames using an LLM."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model

    async def decompose(self, text: str) -> list[str]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(text=text)}],
        )
        return json.loads(response.content[0].text)

    async def classify(self, text: str) -> dict:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(text=text)}],
        )
        return json.loads(response.content[0].text)

    async def normalize(
        self, text: str, source: str = "", domains: list[str] | None = None
    ) -> list[Insight]:
        atoms = await self.decompose(text)
        insights = []
        for atom in atoms:
            classification = await self.classify(atom)
            insights.append(
                Insight(
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
            )
        return insights
