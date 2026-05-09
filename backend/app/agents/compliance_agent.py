"""
Compliance Agent

US-focused safety gate that runs before lead routing.
It validates consent, scans for Fair Housing / risky claims, redacts sensitive PII,
and returns a strict ComplianceResult.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, cast

from pydantic import BaseModel, ConfigDict, Field

from langchain_groq import ChatGroq

from ..core.config import GROQ_API_KEY_AGENTS
from ..core.schemas import ChatMessage, ComplianceResult, LeadProfile


class _ComplianceDetectionLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fair_housing_violations: List[str] = Field(default_factory=list)
    risky_claims: List[str] = Field(default_factory=list)


class ComplianceAgent:
    """
    Deterministic + LLM-assisted compliance gate.

    Deterministic checks:
    - Consent verification
    - PII redaction (SSN, CC/account-like numbers, driver's license mentions)
    - TCPA phone consent logic

    LLM checks (low temperature):
    - Fair Housing Act risk detection
    - Claim blocking (guarantees, ROI promises, unverified urgency, etc.)
    """

    _CONSENT_PROMPT_HINT = "before i save your details so an agent can reach out"

    def __init__(self) -> None:
        self._llm = self._build_llm()

    def _build_llm(self) -> Any:
        api_key = GROQ_API_KEY_AGENTS or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY_AGENTS or GROQ_API_KEY is required for ComplianceAgent.")
        model_name = os.getenv("COMPLIANCE_MODEL", "llama-3.1-8b-instant")
        return ChatGroq(api_key=api_key, model=model_name, temperature=0.2).with_structured_output(
            _ComplianceDetectionLLMOutput
        )

    @staticmethod
    def _normalize_transcript(transcript: Any) -> List[Dict[str, str]]:
        """
        Normalize transcript input to list of {"role": ..., "content": ...}.
        Supports:
        - string transcript
        - list[ChatMessage]
        - list[dict] with role/content
        """
        if isinstance(transcript, str):
            lines = [line.strip() for line in transcript.splitlines() if line.strip()]
            return [{"role": "unknown", "content": line} for line in lines]

        normalized: List[Dict[str, str]] = []
        if isinstance(transcript, Sequence):
            for item in transcript:
                if isinstance(item, ChatMessage):
                    normalized.append({"role": item.role.value, "content": item.content})
                elif isinstance(item, dict):
                    role = str(item.get("role", "unknown"))
                    content = str(item.get("content", ""))
                    if content.strip():
                        normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _find_consent_evidence(messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Log the exact message where consent appears granted.
        """
        yes_patterns = [
            r"\byes\b",
            r"\bi agree\b",
            r"\bok(?:ay)?\b",
            r"\bgo ahead\b",
            r"\bplease do\b",
            r"\bthat'?s fine\b",
            r"\byou have my permission\b",
            r"\bi give (?:you )?permission\b",
            r"\bi consent\b",
            r"\byou can (?:save|store|use) (?:my )?(?:details|info|information)\b",
            r"\byou can contact me\b",
        ]
        yes_re = re.compile("|".join(yes_patterns), re.IGNORECASE)

        # Prefer user confirmation that appears shortly after a consent prompt.
        for idx, msg in enumerate(messages):
            text = msg["content"].lower()
            if ComplianceAgent._CONSENT_PROMPT_HINT in text or "permission" in text:
                for nxt in messages[idx + 1 : idx + 4]:
                    if nxt["role"].lower() == "user" and yes_re.search(nxt["content"]):
                        return nxt["content"]

        # Fallback: first explicit user yes-like consent signal.
        for msg in messages:
            if msg["role"].lower() == "user" and yes_re.search(msg["content"]):
                return msg["content"]
        return None

    @staticmethod
    def _redact_sensitive_pii(raw_text: str) -> tuple[str, bool]:
        """
        Redact unnecessary sensitive PII while preserving operationally useful fields.
        """
        redacted = raw_text
        changed = False

        # SSN patterns: XXX-XX-XXXX or 9 consecutive digits.
        patterns = [
            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            re.compile(r"\b\d{9}\b"),
            # 13-19 digit card-like numbers with spaces/hyphens.
            re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
            # Bank account style mentions.
            re.compile(r"(?i)\b(account|acct)\s*(number|no\.?)?\s*[:#-]?\s*\d{6,17}\b"),
            # Driver's license style mentions followed by id-like token.
            re.compile(r"(?i)\b(driver'?s?\s*license|dl)\s*(number|no\.?)?\s*[:#-]?\s*[A-Z0-9-]{5,20}\b"),
        ]

        for pattern in patterns:
            new_text = pattern.sub("[REDACTED]", redacted)
            if new_text != redacted:
                changed = True
                redacted = new_text

        return redacted, changed

    @staticmethod
    def _format_transcript(messages: List[Dict[str, str]]) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    @staticmethod
    def _has_explicit_phone_marketing_consent(messages: List[Dict[str, str]]) -> bool:
        """
        TCPA explicit consent heuristic: user explicitly agrees to call/text outreach.
        """
        text = "\n".join(m["content"] for m in messages if m["role"].lower() == "user").lower()
        explicit_patterns = [
            r"\byou can call me\b",
            r"\byou can text me\b",
            r"\bi consent to (calls|texts|being contacted)\b",
            r"\bi agree to be contacted\b",
            r"\bcontact me by (phone|text|sms)\b",
        ]
        return any(re.search(p, text) for p in explicit_patterns)

    @staticmethod
    def _has_user_provided_phone(messages: List[Dict[str, str]]) -> bool:
        phone_pattern = re.compile(
            r"(?<!\d)(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}(?!\d)"
        )
        for msg in messages:
            if msg["role"].lower() == "user" and phone_pattern.search(msg["content"]):
                return True
        return False

    async def evaluate(
        self,
        lead_profile: LeadProfile,
        transcript: Any,
    ) -> ComplianceResult:
        """
        Run full compliance checks and return ComplianceResult.
        """
        messages = self._normalize_transcript(transcript)
        transcript_text = self._format_transcript(messages)

        # 1) Consent verification (hard rule)
        consent_evidence = self._find_consent_evidence(messages)
        profile_consent_verified = bool(
            lead_profile.consent_given is True
            and lead_profile.consent_timestamp is not None
        )
        consent_verified = profile_consent_verified

        blocked_claims: List[str] = []
        if not consent_verified:
            blocked_claims.append(
                "CONSENT_MISSING_OR_INCOMPLETE: Lead blocked from routing until explicit consent is verified."
            )
        elif consent_evidence is None:
            blocked_claims.append(
                "CONSENT_LOG_MISSING: Consent flags present but transcript phrase not confidently matched; keep audit trail."
            )

        # 2 + 5) LLM scans for Fair Housing issues and risky claims
        assistant_only_messages = [m for m in messages if m["role"].lower() == "assistant"]
        assistant_text = self._format_transcript(assistant_only_messages)
        llm_out = cast(
            _ComplianceDetectionLLMOutput,
            await self._llm.ainvoke(
                [
                    (
                        "system",
                        (
                            "You are a US real estate compliance auditor. Detect potential Fair Housing Act "
                            "violations and risky marketing/financial claims in assistant messages only.\n"
                            "Return only structured fields.\n"
                            "Be conservative: only flag clear, explicit violations. If unsure, do not flag.\n\n"
                            "Flag ONLY actual violations, for example:\n"
                            "- 'guaranteed 15% returns'\n"
                            "- 'this property will double in value'\n"
                            "- 'you will definitely get approved'\n"
                            "- explicit steering or protected-class discrimination\n\n"
                            "Examples of what is NOT a violation (do NOT flag):\n"
                            "- Asking about financing type (standard intake question)\n"
                            "- Repeating the user's stated timeline (e.g., 'within 1-3 months')\n"
                            "- 'I'll note that down' acknowledgment statements\n"
                            "- Summarizing conversation/preferences\n"
                            "- Offering to assist further / polite closing language\n"
                            "- General non-guaranteed guidance without promises"
                        ),
                    ),
                    (
                        "user",
                        (
                            "Transcript (assistant messages only):\n"
                            f"{assistant_text}\n\n"
                            "Return concise violation strings with short rationale."
                        ),
                    ),
                ]
            ),
        )
        blocked_claims.extend(llm_out.fair_housing_violations)
        blocked_claims.extend(llm_out.risky_claims)

        # 3) Deterministic PII redaction
        sanitized_transcript, pii_redacted = self._redact_sensitive_pii(transcript_text)

        # 4) TCPA check
        if lead_profile.phone:
            explicit_phone_consent = self._has_explicit_phone_marketing_consent(messages)
            user_provided_phone = self._has_user_provided_phone(messages)
            if not explicit_phone_consent and not user_provided_phone and not consent_verified:
                blocked_claims.append("TCPA_MISSING_PHONE_CONSENT: phone present but explicit contact consent not verified.")

        # Include consent evidence log in sanitized transcript.
        consent_log = consent_evidence or "NONE_FOUND"
        sanitized_transcript = (
            f"CONSENT_EVIDENCE: {consent_log}\n"
            f"CONSENT_VERIFIED: {consent_verified}\n"
            f"{sanitized_transcript}"
        )

        # Lead is compliant unless there are clear hard blockers.
        # Keep strict hard blockers for missing consent/TCPA missing consent and explicit LLM violations.
        hard_block_prefixes = (
            "CONSENT_MISSING_OR_INCOMPLETE",
            "TCPA_MISSING_PHONE_CONSENT",
        )
        hard_block = any(
            claim.startswith(hard_block_prefixes) for claim in blocked_claims
        ) or bool(llm_out.fair_housing_violations or llm_out.risky_claims)

        compliant = not hard_block and consent_verified

        return ComplianceResult(
            lead_id=lead_profile.id,
            consent_verified=consent_verified,
            pii_redacted=pii_redacted,
            blocked_claims=blocked_claims,
            sanitized_transcript=sanitized_transcript,
            compliant=compliant,
            timestamp=datetime.now(timezone.utc),
        )


