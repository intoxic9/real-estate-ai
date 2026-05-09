"""
Scoring Agent

Deterministic lead heat scoring for US real estate.
LLM is used only to generate concise reasoning signals.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, cast

from pydantic import BaseModel, ConfigDict, Field

from langchain_groq import ChatGroq

from ..core.config import GROQ_API_KEY_AGENTS
from ..core.schemas import (
    ChatMessage,
    FinancingType,
    IntentResult,
    LeadProfile,
    LeadTimeline,
    ScoreBucket,
    ScoreResult,
)


class _ReasoningOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signals: List[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _Weights:
    timeline: float
    budget_clarity: float
    location_specificity: float
    prequalification: float
    intent_confidence: float
    engagement_quality: float
    consent_contact: float


class ScoringAgent:
    """Deterministic scorer with configurable weights."""

    def __init__(self) -> None:
        self.weights = _Weights(
            timeline=float(os.getenv("SCORING_WEIGHT_TIMELINE", "25")),
            budget_clarity=float(os.getenv("SCORING_WEIGHT_BUDGET_CLARITY", "20")),
            location_specificity=float(os.getenv("SCORING_WEIGHT_LOCATION_SPECIFICITY", "15")),
            prequalification=float(os.getenv("SCORING_WEIGHT_PREQUALIFICATION", "15")),
            intent_confidence=float(os.getenv("SCORING_WEIGHT_INTENT_CONFIDENCE", "10")),
            engagement_quality=float(os.getenv("SCORING_WEIGHT_ENGAGEMENT_QUALITY", "10")),
            consent_contact=float(os.getenv("SCORING_WEIGHT_CONSENT_CONTACT", "5")),
        )
        self._llm = self._build_reasoning_llm()

    @staticmethod
    def _build_reasoning_llm() -> Optional[Any]:
        api_key = GROQ_API_KEY_AGENTS or os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        model = os.getenv("SCORING_REASONING_MODEL", "llama-3.1-8b-instant")
        return ChatGroq(api_key=api_key, model=model, temperature=0.3).with_structured_output(
            _ReasoningOutput
        )

    @staticmethod
    def _normalize_transcript(transcript: Any) -> List[str]:
        if isinstance(transcript, str):
            return [line.strip() for line in transcript.splitlines() if line.strip()]

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
        return lines

    @staticmethod
    def _timeline_raw(lead: LeadProfile) -> float:
        if lead.timeline == LeadTimeline.immediate:
            return 25.0
        if lead.timeline == LeadTimeline.one_to_three_months:
            return 18.0
        if lead.timeline == LeadTimeline.three_to_six_months:
            return 12.0
        if lead.timeline == LeadTimeline.six_to_twelve_months:
            return 6.0
        return 2.0

    @staticmethod
    def _budget_raw(lead: LeadProfile, transcript_text: str) -> float:
        if lead.budget_min is not None and lead.budget_max is not None:
            return 20.0
        if lead.budget_min is not None or lead.budget_max is not None:
            return 12.0
        if re.search(r"\b(around|about|roughly|approx(?:imately)?)\s*\$?\s*\d", transcript_text, re.IGNORECASE):
            return 12.0
        if re.search(r"\$\s*\d{2,3}[kK]\b|\b\d{2,3}[kK]\b", transcript_text):
            return 12.0
        return 3.0

    @staticmethod
    def _location_raw(lead: LeadProfile) -> float:
        locations = [x.strip() for x in lead.preferred_locations if isinstance(x, str) and x.strip()]
        target = (lead.target_market or "").strip()

        # Specific city + neighborhood
        if len(locations) >= 2:
            return 15.0
        if any("," in loc for loc in locations):  # e.g., "Austin, Mueller"
            return 15.0

        # Specific city only
        if locations or target:
            # Heuristic: "Metro", state abbreviations, or region words = less specific.
            tgt = target.lower()
            if any(x in tgt for x in (" metro", " county", " region")) or re.search(r"\b[a-z]{2}\b", tgt):
                return 5.0
            return 10.0
        return 2.0

    @staticmethod
    def _prequalification_raw(lead: LeadProfile, transcript_text: str) -> float:
        t = transcript_text.lower()
        if lead.financing_type == FinancingType.cash or "cash buyer" in t:
            return 15.0
        if "pre-approved" in t or "pre approved" in t:
            return 15.0
        if "pre-qualified" in t or "pre qualified" in t:
            return 10.0
        if "talked to a lender" in t or "spoke to a lender" in t or "lender" in t:
            return 6.0
        return 2.0

    @staticmethod
    def _intent_confidence_raw(intent: IntentResult) -> float:
        c = intent.confidence
        if c > 0.8:
            return 10.0
        if c >= 0.6:
            return 7.0
        return 2.0

    @staticmethod
    def _engagement_raw(messages: List[str]) -> float:
        user_messages = [m for m in messages if m.lower().startswith("user:")]
        total_user = len(user_messages)
        questions = sum(1 for m in user_messages if "?" in m)
        long_msgs = sum(1 for m in user_messages if len(m) >= 90)
        if total_user >= 4 and (questions >= 2 or long_msgs >= 2):
            return 10.0
        if total_user >= 2:
            return 5.0
        return 2.0

    @staticmethod
    def _consent_contact_raw(lead: LeadProfile) -> float:
        if lead.consent_given and lead.phone and lead.email:
            return 5.0
        if lead.consent_given and lead.email:
            return 3.0
        if lead.consent_given:
            return 2.0
        return 0.0

    def _weighted_score(self, raw: Dict[str, float]) -> float:
        """
        Compute weighted score and normalize to 0-100 even if env weights change.
        """
        max_raw = {
            "timeline": 25.0,
            "budget_clarity": 20.0,
            "location_specificity": 15.0,
            "prequalification": 15.0,
            "intent_confidence": 10.0,
            "engagement_quality": 10.0,
            "consent_contact": 5.0,
        }
        weights = self.weights
        weighted_sum = (
            (raw["timeline"] / max_raw["timeline"]) * weights.timeline
            + (raw["budget_clarity"] / max_raw["budget_clarity"]) * weights.budget_clarity
            + (raw["location_specificity"] / max_raw["location_specificity"]) * weights.location_specificity
            + (raw["prequalification"] / max_raw["prequalification"]) * weights.prequalification
            + (raw["intent_confidence"] / max_raw["intent_confidence"]) * weights.intent_confidence
            + (raw["engagement_quality"] / max_raw["engagement_quality"]) * weights.engagement_quality
            + (raw["consent_contact"] / max_raw["consent_contact"]) * weights.consent_contact
        )
        total_weight = (
            weights.timeline
            + weights.budget_clarity
            + weights.location_specificity
            + weights.prequalification
            + weights.intent_confidence
            + weights.engagement_quality
            + weights.consent_contact
        )
        if total_weight <= 0:
            return 0.0
        return max(0.0, min(100.0, (weighted_sum / total_weight) * 100.0))

    @staticmethod
    def _bucket(score: int) -> ScoreBucket:
        if score >= 60:
            return ScoreBucket.hot
        if score >= 35:
            return ScoreBucket.warm
        return ScoreBucket.cold

    async def _reasoning_signals(
        self,
        lead: LeadProfile,
        intent: IntentResult,
        raw: Dict[str, float],
        final_score: int,
        bucket: ScoreBucket,
        transcript_lines: List[str],
    ) -> List[str]:
        deterministic_signals = [
            f"Timeline signal: {raw['timeline']:.0f}/25",
            f"Budget clarity signal: {raw['budget_clarity']:.0f}/20",
            f"Location specificity signal: {raw['location_specificity']:.0f}/15",
            f"Pre-qualification signal: {raw['prequalification']:.0f}/15",
            f"Intent confidence signal: {raw['intent_confidence']:.0f}/10",
            f"Engagement quality signal: {raw['engagement_quality']:.0f}/10",
            f"Consent/contact signal: {raw['consent_contact']:.0f}/5",
            f"Final heat score: {final_score} ({bucket.value})",
        ]

        if not self._llm:
            return deterministic_signals

        transcript_preview = "\n".join(transcript_lines[:12])
        llm_out = cast(
            _ReasoningOutput,
            await self._llm.ainvoke(
                [
                    (
                        "system",
                        "You explain lead scoring results. Do NOT change numbers. Return short bullet-like signals.",
                    ),
                    (
                        "user",
                        (
                            f"Lead profile: {lead.model_dump()}\n"
                            f"Intent result: {intent.model_dump()}\n"
                            f"Deterministic component scores: {raw}\n"
                            f"Final score: {final_score}, bucket: {bucket.value}\n"
                            f"Transcript preview:\n{transcript_preview}\n"
                            "Generate 5-8 concise reasoning signals aligned with the deterministic score."
                        ),
                    ),
                ]
            ),
        )
        signals = [s.strip() for s in llm_out.signals if s.strip()]
        return signals or deterministic_signals

    async def score(
        self,
        lead_profile: LeadProfile,
        intent_result: IntentResult,
        transcript: Any,
    ) -> ScoreResult:
        """
        Deterministically compute heat score (0-100), assign bucket, and attach reasoning signals.
        """
        transcript_lines = self._normalize_transcript(transcript)
        transcript_text = "\n".join(transcript_lines)

        raw = {
            "timeline": self._timeline_raw(lead_profile),
            "budget_clarity": self._budget_raw(lead_profile, transcript_text),
            "location_specificity": self._location_raw(lead_profile),
            "prequalification": self._prequalification_raw(lead_profile, transcript_text),
            "intent_confidence": self._intent_confidence_raw(intent_result),
            "engagement_quality": self._engagement_raw(transcript_lines),
            "consent_contact": self._consent_contact_raw(lead_profile),
        }
        score_value = int(round(self._weighted_score(raw)))
        bucket = self._bucket(score_value)
        signals = await self._reasoning_signals(
            lead=lead_profile,
            intent=intent_result,
            raw=raw,
            final_score=score_value,
            bucket=bucket,
            transcript_lines=transcript_lines,
        )

        return ScoreResult(
            lead_id=lead_profile.id,
            heat_score=score_value,
            bucket=bucket,
            signals=signals,
            timestamp=datetime.now(timezone.utc),
        )


