"""
Intent Agent

Classifies lead intent for US real estate use-cases using:
- LeadProfile context
- Full conversation transcript
- 3-pass LLM voting for calibration
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, cast

from pydantic import BaseModel, ConfigDict, Field

from langchain_groq import ChatGroq

from ..core.config import GROQ_API_KEY_AGENTS
from ..core.schemas import ChatMessage, IntentResult, LeadIntent, LeadProfile


class _IntentLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: LeadIntent
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: List[str] = Field(default_factory=list)


class IntentAgent:
    """
    Intent classification agent.

    Classification set:
    - buyer_primary
    - buyer_investment
    - seller
    - renter
    - refinance
    - unknown
    """

    def __init__(self) -> None:
        self._api_key = GROQ_API_KEY_AGENTS or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise RuntimeError("GROQ_API_KEY_AGENTS or GROQ_API_KEY is required for IntentAgent.")
        self._model_name = os.getenv("INTENT_MODEL", "llama-3.3-70b-versatile")
        self._temperatures = (0.3, 0.3, 0.3)

    @staticmethod
    def _normalize_transcript(transcript: Any) -> str:
        if isinstance(transcript, str):
            return transcript

        lines: List[str] = []
        if isinstance(transcript, Sequence):
            for item in transcript:
                if isinstance(item, ChatMessage):
                    lines.append(f"{item.role.value}: {item.content}")
                elif isinstance(item, dict):
                    role = str(item.get("role", "unknown"))
                    content = str(item.get("content", ""))
                    if content.strip():
                        lines.append(f"{role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _system_prompt() -> str:
        return """
You are an intent-classification specialist for US real estate leads.

Your task:
- Analyze lead profile + transcript
- Classify into exactly one:
  - buyer_primary
  - buyer_investment
  - seller
  - renter
  - refinance
  - unknown

Intent signal hints:
- first-time buyer / FHA / down payment assistance -> buyer_primary
- rental income / cap rate / 1031 exchange / investment property -> buyer_investment
- I need to sell / listing / what's my home worth / CMA -> seller
- apartment / lease / monthly rent / pet-friendly -> renter
- lower my rate / refinance / home equity -> refinance
- relocating for work / moving to [city] -> likely buyer_primary
- house hack / duplex / multi-family -> buyer_investment

Rules:
- Use evidence from both transcript and profile.
- Keep rationale concise and evidence-based.
- Confidence is [0.0, 1.0].
- If evidence is weak/ambiguous, choose unknown with lower confidence.

Return ONLY the structured output.
""".strip()

    async def _run_once(
        self,
        lead_profile: LeadProfile,
        transcript_text: str,
        temperature: float,
    ) -> _IntentLLMOutput:
        llm = ChatGroq(api_key=self._api_key, model=self._model_name, temperature=temperature).with_structured_output(
            _IntentLLMOutput
        )
        result = cast(
            _IntentLLMOutput,
            await llm.ainvoke(
                [
                    ("system", self._system_prompt()),
                    (
                        "user",
                        (
                            "LeadProfile:\n"
                            f"{lead_profile.model_dump()}\n\n"
                            "Transcript:\n"
                            f"{transcript_text}\n\n"
                            "Classify intent."
                        ),
                    ),
                ]
            ),
        )
        return result

    async def classify(
        self,
        lead_profile: LeadProfile,
        transcript: Any,
    ) -> IntentResult:
        """
        Run 3 classifications with different temperatures and apply majority vote.
        If final confidence < 0.6, force classification to unknown and flag in rationale.
        """
        transcript_text = self._normalize_transcript(transcript)

        results: List[_IntentLLMOutput] = []
        for temp in self._temperatures:
            results.append(await self._run_once(lead_profile, transcript_text, temp))

        class_votes = Counter(r.classification for r in results)
        voted_class = class_votes.most_common(1)[0][0]

        # Calibrate confidence by averaging confidence among the winning class votes.
        conf_values = [r.confidence for r in results if r.classification == voted_class]
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        # Merge rationale snippets (de-duplicated while preserving order).
        merged_rationale: List[str] = []
        seen: Dict[str, bool] = defaultdict(bool)
        for r in results:
            for item in r.rationale:
                k = item.strip()
                if k and not seen[k]:
                    seen[k] = True
                    merged_rationale.append(k)

        # Enforce user rule: low confidence => unknown + human review flag.
        final_class = voted_class
        final_conf = max(0.0, min(1.0, avg_conf))
        if final_conf < 0.6:
            final_class = LeadIntent.unknown
            merged_rationale.append("Flagged for human review due to low confidence (< 0.6).")

        # Keep to requested categories (plus unknown) even though LeadIntent supports legacy values.
        allowed = {
            LeadIntent.buyer_primary,
            LeadIntent.buyer_investment,
            LeadIntent.seller,
            LeadIntent.renter,
            LeadIntent.refinance,
            LeadIntent.unknown,
        }
        if final_class not in allowed:
            final_class = LeadIntent.unknown
            merged_rationale.append("Mapped to unknown because classification was outside allowed categories.")

        if not merged_rationale:
            merged_rationale = ["Insufficient explicit intent cues found in transcript/profile."]

        return IntentResult(
            lead_id=lead_profile.id,
            classification=final_class,
            confidence=final_conf,
            rationale=merged_rationale,
            timestamp=datetime.now(timezone.utc),
        )


