"""
Conversation Agent

Adaptive lead intake through natural conversation for the US real estate market.

Key constraints:
- Never collect/store PII (full_name/email/phone) until explicit consent is given.
- Never guarantee returns, appreciation, or future prices.
- If user asks legal/tax/mortgage matters, recommend a licensed professional.
"""

from __future__ import annotations

import os
import re
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field

from langchain_groq import ChatGroq
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import GROQ_API_KEY_CHAT
from ..core.schemas import (
    ChatRole,
    ConversationTranscriptORM,
    FinancingType,
    LeadIntent,
    LeadProfile,
    LeadTimeline,
    PropertyType,
)

logger = logging.getLogger(__name__)


class ConversationStage(str, Enum):
    GREETING = "GREETING"
    INTENT_DISCOVERY = "INTENT_DISCOVERY"
    DETAILS_COLLECTION = "DETAILS_COLLECTION"
    PERSONAL_INFO = "PERSONAL_INFO"
    CONSENT = "CONSENT"
    SUMMARY = "SUMMARY"


PII_FIELDS = {"full_name", "email", "phone"}


class ConversationState(TypedDict, total=False):
    stage: str
    lead_profile: Dict[str, Any]
    consent_given: bool
    consent_requested: bool
    analytics_only: bool
    turn_count: int
    intent_locked: bool
    locked_intent: str


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str
    lead_profile_updates: Dict[str, Any] = Field(default_factory=dict)
    stage: str
    is_complete: bool
    consent_requested: bool
    consent_given: bool
    widget: Optional[Dict[str, Any]] = None


class _LLMOutput(BaseModel):
    """
    Structured output produced by the LLM.

    Note: We keep fields flexible (Dict[str, Any]) for `lead_profile_updates` because we
    are producing partial updates; final validation happens when constructing the full lead.
    """

    model_config = ConfigDict(extra="forbid")

    response: str
    stage: ConversationStage
    lead_profile_updates: Dict[str, Any] = Field(default_factory=dict)
    consent_requested: bool = False
    consent_given: bool = False
    analytics_only: bool = False


def _company_name() -> str:
    return os.getenv("COMPANY_NAME", "810 Realty")


def _system_prompt() -> str:
    company = _company_name()
    return f"""
You are a knowledgeable US real estate AI assistant for {company}. You help potential buyers,
sellers, renters, and investors find what they need.

Your knowledge includes:
- Major US metro markets: NYC, Los Angeles, Miami, Chicago, Dallas-Fort Worth, Austin, Denver,
  Seattle, Phoenix, Atlanta, Nashville, Charlotte, Tampa, Raleigh, and more
- Typical price ranges by city and neighborhood
- Property types: single-family homes, condos, co-ops, townhouses, multi-family, land
- Financing options: conventional mortgages, FHA loans, VA loans, cash purchases, jumbo loans
- First-time buyer programs and down payment assistance
- Investment considerations: rental yield, appreciation, cap rates, 1031 exchanges
- Market conditions: inventory levels, days on market, bidding wars vs buyer's market

Your tone: Professional, helpful, and knowledgeable. Like a trusted friend who happens to be
a real estate expert.

RULES YOU MUST FOLLOW:
1. Never guarantee specific returns, appreciation rates, or future prices
2. Never provide specific legal, tax, or mortgage advice - recommend they consult a licensed professional
3. Never make claims about school quality that could violate Fair Housing Act (avoid steering)
4. Always get explicit consent before storing personal information:
   "Before I save your details so an agent can reach out, I need your permission. Is that okay?"
5. If asked about neighborhood demographics, racial composition, or "safety," redirect to publicly available
   data sources rather than making characterizations (Fair Housing compliance)
6. Never ask about race, religion, national origin, familial status, disability, or sex - these are protected
   classes under Fair Housing Act

Behavior:
- Maintain stage flow: GREETING -> INTENT_DISCOVERY -> DETAILS_COLLECTION -> PERSONAL_INFO -> CONSENT -> SUMMARY
- Ask only the minimum necessary questions based on known data
- Handle missing information gracefully (never force answers)
- If user declines PII sharing, offer analytics-only mode
- Speak naturally, never like a rigid form

IMPORTANT: You MUST ask for and collect the user's name before asking for consent.
You must also collect either an email address or phone number. Never skip these fields.
Ask naturally:
- "What's your name?" or "Who am I speaking with today?"
- "Could I get your name and the best way to reach you?"
These are required for our team to follow up.
When collecting personal information, ALWAYS ask for the user's preferred name along with their
contact info. Ask both in one message, naturally: "Could I get your name and the best way to
reach you?" Never skip asking for the name.

Extraction rules for lead_profile_updates:
- Capture partial fields when user provides them: intent, target_market, preferred_locations,
  timeline, property_type, budget_min, budget_max, financing_type, is_first_time_buyer, source.
- Capture full_name, email, and phone when provided so you can complete PERSONAL_INFO before CONSENT.
- If consent is denied, set analytics_only=true.

Return ONLY a JSON object matching the output schema.
""".strip()


def _model_name() -> str:
    return os.getenv("CONVERSATION_MODEL", "llama-3.3-70b-versatile")


def _llm() -> ChatGroq:
    api_key = GROQ_API_KEY_CHAT or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY_CHAT or GROQ_API_KEY is required for ConversationAgent.")
    return ChatGroq(api_key=api_key, model=_model_name(), temperature=0.7)


def _safe_bool(x: Any) -> bool:
    return bool(x) is True


def _detect_consent_from_user_text(text: str) -> Optional[bool]:
    """
    Simple heuristic to help the state machine when the user replies to the consent prompt.
    The LLM also outputs consent flags, but this adds a deterministic layer.
    """
    t = text.strip().lower()
    yes = {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "i agree",
        "agreed",
        "go ahead",
        "please do",
        "yes thats alright",
        "yes that's alright",
        "you can save my info",
        "you have my permission",
    }
    no = {"no", "n", "nope", "not ok", "not okay", "i don't agree", "dont agree", "decline"}
    if any(p in t for p in yes):
        return True
    if any(p in t for p in no):
        return False
    return None


def _heuristic_updates_from_text(text: str) -> Dict[str, Any]:
    """
    Deterministic extraction for high-signal fields to avoid LLM misses.
    """
    t = text.lower()
    updates: Dict[str, Any] = {}

    # Preliminary intent extraction for progressive UI updates during conversation.
    buy_signals = ["buy", "purchase", "first home", "first-time buyer", "first time buyer"]
    uncertain_buy_context = [
        "not sure",
        "not really sure",
        "just browsing",
        "just curious",
        "maybe someday",
        "just looking",
    ]
    owner_signals = [
        "i own",
        "my property",
        "my house",
        "my apartment",
        "rent it out",
        "list it",
        "sell my property",
        "i want to sell",
    ]
    landlord_signals = [
        "rent it out",
        "rent out",
        "looking for tenants",
        "find tenants",
        "rental income",
        "tenants",
    ]
    renter_seeker_signals = ["i want to rent", "i'm looking for", "im looking for", "i need"]
    if any(x in t for x in landlord_signals):
        updates["intent"] = LeadIntent.seller
        updates["sub_intent"] = "landlord"
    elif any(x in t for x in owner_signals):
        updates["intent"] = LeadIntent.seller
    elif any(x in t for x in buy_signals) and any(x in t for x in uncertain_buy_context):
        updates["intent"] = LeadIntent.unknown
    elif any(x in t for x in ["refinance", "lower my rate", "home equity"]):
        updates["intent"] = LeadIntent.refinance
    elif any(x in t for x in ["invest", "rental income", "flip", "investment property", "cap rate", "1031"]):
        updates["intent"] = LeadIntent.buyer_investment
    elif any(x in t for x in ["sell", "listing", "what's my home worth", "whats my home worth", "cma"]):
        updates["intent"] = LeadIntent.seller
    elif any(x in t for x in ["rent", "lease", "apartment"]) and any(
        x in t for x in renter_seeker_signals
    ):
        updates["intent"] = LeadIntent.renter
    elif any(x in t for x in buy_signals):
        updates["intent"] = LeadIntent.buyer_primary

    # Personal info extraction.
    name_patterns = [
        r"\bmy name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        r"\bi am\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        r"\bi'm\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        r"\bthis is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        r"\bcall me\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            updates["full_name"] = match.group(1).strip()
            break
    if "full_name" not in updates:
        proper_name_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text)
        if proper_name_match:
            updates["full_name"] = proper_name_match.group(1).strip()

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone_match = re.search(r"[\+]?\s*1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text)
    if email_match:
        updates["email"] = email_match.group()
    if phone_match:
        updates["phone"] = phone_match.group().strip()

    # Financing extraction.
    if "fha" in t:
        updates["financing_type"] = FinancingType.fha
    elif re.search(r"\bva\b", t):
        updates["financing_type"] = FinancingType.va
    elif "cash buyer" in t or re.search(r"\bcash\b", t):
        updates["financing_type"] = FinancingType.cash
    elif "conventional" in t:
        updates["financing_type"] = FinancingType.conventional

    # Property type extraction.
    if any(x in t for x in ["single family", "single-family", "single_family"]):
        updates["property_type"] = PropertyType.single_family
    elif any(x in t for x in ["townhouse", "townhome"]):
        updates["property_type"] = PropertyType.townhouse
    elif any(x in t for x in ["condo", "condominium", "co-op", "coop", "apartment"]):
        updates["property_type"] = PropertyType.apartment
    elif "land" in t:
        updates["property_type"] = PropertyType.land
    elif "commercial" in t or "retail" in t or "office" in t:
        updates["property_type"] = PropertyType.commercial

    # Timeline extraction.
    if any(x in t for x in ["just exploring", "exploring", "just browsing", "not sure yet"]):
        updates["timeline"] = LeadTimeline.exploring
    elif "asap" in t or "immediately" in t or re.search(r"\bmove\s+asap\b", t) or re.search(r"under\s+30\s+days", t):
        updates["timeline"] = LeadTimeline.immediate
    elif (
        "1-3 months" in t
        or "1 to 3 months" in t
        or "1_3_months" in t
        or re.search(r"\b(i need to move in|move in|within|in)\s+(1|2|3)\s+months?\b", t)
        or re.search(r"\bnext\s+(1|2|3)\s+months?\b", t)
    ):
        updates["timeline"] = LeadTimeline.one_to_three_months
    elif (
        "3-6 months" in t
        or "3 to 6 months" in t
        or "3_6_months" in t
        or re.search(r"\b(in|within|next)\s+(4|5|6)\s+months?\b", t)
        or re.search(r"\b6\s+months?\b", t)
    ):
        updates["timeline"] = LeadTimeline.three_to_six_months
    elif (
        "6-12 months" in t
        or "6 to 12 months" in t
        or "6_12_months" in t
        or re.search(r"\b(in|within|next)\s+(7|8|9|10|11|12)\s+months?\b", t)
        or "a year" in t
        or "1 year" in t
        or "one year" in t
    ):
        updates["timeline"] = LeadTimeline.six_to_twelve_months

    return updates


def _is_complete(lead_profile: Dict[str, Any], consent_given: bool, analytics_only: bool) -> bool:
    """
    "Complete" means we have enough to either:
    - proceed with lead capture (details + consent), or
    - proceed in analytics-only mode (details, no PII).
    """
    # Critical, non-PII fields for meaningful intake.
    critical = {"intent", "property_type", "timeline", "preferred_locations"}
    has_critical = all(k in lead_profile and lead_profile.get(k) not in (None, "", []) for k in critical)

    if analytics_only:
        return has_critical

    # If not analytics-only, require consent before treating intake as complete.
    return has_critical and consent_given


def _redact_transcript_pii(text: str) -> str:
    """
    Redact PII from transcript messages before persisting to the database.
    """
    email_pattern = re.compile(
        r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    )
    phone_pattern = re.compile(
        r"(?<!\d)(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)\d{3}[\s\-\.]?\d{4}(?!\d)"
    )
    redacted = email_pattern.sub("[REDACTED_EMAIL]", text)
    redacted = phone_pattern.sub("[REDACTED_PHONE]", redacted)
    return redacted


def _strip_pii(updates: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in updates.items() if k not in PII_FIELDS}


def _normalize_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerce some common representations into our enums/shape.
    Keeps this conservative to avoid surprising conversions.
    """
    normalized: Dict[str, Any] = dict(updates or {})

    # Normalize intent/timeline/property_type if LLM returns raw strings.
    if "intent" in normalized and isinstance(normalized["intent"], str):
        try:
            normalized["intent"] = LeadIntent(normalized["intent"])
        except Exception:
            normalized["intent"] = LeadIntent.unknown

    if "timeline" in normalized and isinstance(normalized["timeline"], str):
        try:
            normalized["timeline"] = LeadTimeline(normalized["timeline"])
        except Exception:
            normalized.pop("timeline", None)

    if "property_type" in normalized and isinstance(normalized["property_type"], str):
        raw_property_type = normalized["property_type"].strip().lower()
        property_aliases = {
            "single-family": "single_family",
            "single family": "single_family",
            "single_family": "single_family",
            "house": "single_family",
            "home": "single_family",
            "condo": "apartment",
            "condominium": "apartment",
            "co-op": "apartment",
            "coop": "apartment",
            "townhome": "townhouse",
            "multi-family": "commercial",
            "multifamily": "commercial",
        }
        raw_property_type = property_aliases.get(raw_property_type, raw_property_type)
        try:
            normalized["property_type"] = PropertyType(raw_property_type)
        except Exception:
            normalized.pop("property_type", None)

    if "financing_type" in normalized and isinstance(normalized["financing_type"], str):
        raw_financing = normalized["financing_type"].strip().lower()
        financing_aliases = {
            "jumbo": "other",
            "jumbo loan": "other",
            "mortgage": "conventional",
        }
        raw_financing = financing_aliases.get(raw_financing, raw_financing)
        try:
            normalized["financing_type"] = FinancingType(raw_financing)
        except Exception:
            normalized["financing_type"] = FinancingType.unknown

    # Preferred locations should be a list[str].
    if "preferred_locations" in normalized and isinstance(normalized["preferred_locations"], str):
        normalized["preferred_locations"] = [normalized["preferred_locations"]]

    # Guard against accidental bucket/score fields being injected here.
    for forbidden in ("bucket", "heat_score", "latest_score", "score_bucket", "score"):
        if forbidden in normalized:
            normalized.pop(forbidden, None)

    return normalized


def _filter_allowed_lead_update_fields(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Only allow fields that exist on LeadProfile so unexpected LLM fields do not
    poison session state or crash downstream model construction.
    """
    allowed_fields = set(LeadProfile.model_fields.keys())
    # Allow non-persistent conversation hints used by the state machine/UI.
    allowed_fields |= {"sub_intent"}
    return {k: v for k, v in updates.items() if k in allowed_fields}


def _drop_empty_values(updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove empty-string/noisy values from partial LLM updates while preserving
    valid False/0 values.
    """
    cleaned: Dict[str, Any] = {}
    for key, value in updates.items():
        if isinstance(value, str) and value.strip() == "":
            continue
        if isinstance(value, list):
            non_empty_items = [
                item for item in value if not (isinstance(item, str) and item.strip() == "")
            ]
            cleaned[key] = non_empty_items
            continue
        cleaned[key] = value
    return cleaned


def _has_uncertain_buy_intent(text: str) -> bool:
    t = text.lower()
    buy_signals = ("buy", "purchase", "first home", "first-time buyer", "first time buyer")
    uncertain_signals = ("not sure", "not really sure", "just browsing", "just curious", "maybe someday", "just looking")
    has_buy_signal = any(signal in t for signal in buy_signals)
    has_uncertain_signal = any(signal in t for signal in uncertain_signals)
    return has_buy_signal and has_uncertain_signal


def _has_owner_seller_intent(text: str) -> bool:
    t = text.lower()
    owner_signals = (
        "i own",
        "my property",
        "my house",
        "my apartment",
        "rent it out",
        "list it",
        "sell my property",
        "i want to sell",
        "put it on the market",
        "what's my home worth",
        "whats my home worth",
        "home valuation",
        "home worth",
        "cma",
        "rent out",
        "looking for tenants",
        "find tenants",
        "rental income",
    )
    return any(signal in t for signal in owner_signals)


def _has_explicit_intent_change(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in ("actually", "instead", "change intent", "not sell", "not renting"))


def _has_explicit_buy_override(text: str) -> bool:
    """
    Unlock seller intent ONLY when the user clearly switches to buying.
    Target examples:
      - "actually I want to buy instead"
      - "instead of selling, I'm buying"
    """
    t = text.lower()
    buy_keywords = ("buy", "purchase", "first home", "first-time buyer", "first time buyer")
    switch_keywords = ("actually", "instead", "rather than", "switching")
    return any(k in t for k in switch_keywords) and any(k in t for k in buy_keywords)


def _is_landlord_message(text: str) -> bool:
    t = text.lower()
    return any(
        phrase in t
        for phrase in (
            "rent it out",
            "rent out",
            "looking for tenants",
            "find tenants",
            "rental income",
            "tenants",
        )
    )


def _is_field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _has_required_personal_info(lead_profile: Dict[str, Any]) -> bool:
    has_name = _is_field_present(lead_profile.get("full_name"))
    has_contact = _is_field_present(lead_profile.get("email")) or _is_field_present(
        lead_profile.get("phone")
    )
    return has_name and has_contact


def _missing_fields_for_flow(lead_profile: Dict[str, Any], intent: LeadIntent, consent_given: bool) -> list[str]:
    """
    Determine which fields are still missing by intent flow so we can avoid
    asking already-answered questions and prevent circular loops.
    """
    if intent == LeadIntent.seller:
        required = ["property_type", "preferred_locations", "timeline"]
        # For seller pricing (and landlord asking rent), accept either budget_min or budget_max.
        has_price = _is_field_present(lead_profile.get("budget_min")) or _is_field_present(lead_profile.get("budget_max"))
        missing = [field for field in required if not _is_field_present(lead_profile.get(field))]
        if not has_price:
            missing.append("asking_price_or_rent")

        # Buyer/tenant requirements are approximated by whether a financing preference is known.
        financing_type = lead_profile.get("financing_type")
        if financing_type is None or financing_type == FinancingType.unknown:
            missing.append("buyer_or_tenant_requirements")
    else:
        required = ["intent", "property_type", "preferred_locations", "timeline"]
        missing = [field for field in required if not _is_field_present(lead_profile.get(field))]
        if intent in {LeadIntent.buyer_primary, LeadIntent.buyer_investment}:
            if not (
                _is_field_present(lead_profile.get("budget_min"))
                or _is_field_present(lead_profile.get("budget_max"))
            ):
                missing.append("budget")

    if not consent_given:
        missing.append("consent")
    return missing


def _build_widget_for_turn(
    *,
    previous_stage: ConversationStage,
    response_text: str,
    missing_fields: list[str],
) -> Optional[Dict[str, Any]]:
    text = response_text.lower()

    # After greeting.
    if previous_stage == ConversationStage.GREETING:
        return {
            "type": "quick_replies",
            "options": ["Primary Residence", "Investment Property", "Vacation Home"],
        }

    # After asking property type.
    if "what type of property" in text:
        return {
            "type": "quick_replies",
            "options": ["Single Family", "Condo/Apartment", "Townhouse"],
        }

    # After asking timeline.
    if "when are you hoping" in text or "timeline" in text:
        return {
            "type": "quick_replies",
            "options": ["ASAP", "1-3 Months", "6+ Months", "Just Exploring"],
        }

    # After asking budget/price.
    if (
        "budget" in text
        or "asking price" in text
        or "estimated value" in text
        or "asking rent" in text
        or "asking_price_or_rent" in missing_fields
    ):
        return {
            "type": "budget_slider",
            "min": 50000,
            "max": 2000000,
        }

    return None


class ConversationAgent:
    """
    Manages adaptive lead intake through natural conversation.

    Usage:
        agent = ConversationAgent()
        result, new_state = await agent.handle_turn(message, state)
    """

    def __init__(self) -> None:
        self._llm = _llm().with_structured_output(_LLMOutput)

    async def handle_turn(
        self,
        user_message: str,
        state: Optional[ConversationState] = None,
        session_id: str = "",
        db: Optional[AsyncSession] = None,
    ) -> tuple[AgentTurnResult, ConversationState]:
        state = state or {}
        stage = ConversationStage(state.get("stage") or ConversationStage.GREETING.value)
        lead_profile: Dict[str, Any] = dict(state.get("lead_profile") or {})

        # Persist user message to transcript table (PII redacted).
        if db is not None and session_id:
            db.add(
                ConversationTranscriptORM(
                    session_id=session_id,
                    lead_id=None,
                    role=ChatRole.user,
                    content=_redact_transcript_pii(user_message),
                    timestamp=datetime.now(timezone.utc),
                )
            )
        consent_given = _safe_bool(state.get("consent_given"))
        consent_requested = _safe_bool(state.get("consent_requested"))
        analytics_only = _safe_bool(state.get("analytics_only"))
        turn_count = int(state.get("turn_count") or 0) + 1
        intent_locked = _safe_bool(state.get("intent_locked"))
        locked_intent_raw = state.get("locked_intent")
        locked_intent = (
            LeadIntent(locked_intent_raw)
            if isinstance(locked_intent_raw, str) and locked_intent_raw in LeadIntent._value2member_map_
            else None
        )
        consent_just_granted = False

        # Deterministic consent detection globally once consent was requested.
        maybe = _detect_consent_from_user_text(user_message)
        if stage == ConversationStage.CONSENT or consent_requested:
            if maybe is True:
                consent_given = True
                consent_just_granted = True
                consent_requested = True
            elif maybe is False:
                consent_given = False
                consent_requested = True
                analytics_only = True

        prompt_context = {
            "current_stage": stage.value,
            "known_lead_profile": lead_profile,
            "consent_given": consent_given,
            "consent_requested": consent_requested,
            "analytics_only": analytics_only,
            "turn_count": turn_count,
            "user_message": user_message,
        }

        # LangChain's type hints for structured output are broad (dict | BaseModel),
        # but at runtime `with_structured_output(_LLMOutput)` returns `_LLMOutput`.
        try:
            llm_out = cast(
                _LLMOutput,
                await self._llm.ainvoke(
                    [
                        ("system", _system_prompt()),
                        (
                            "user",
                            f"Context: {prompt_context}\n\nUser said: {user_message}",
                        ),
                    ]
                ),
            )
        except Exception as exc:  # noqa: BLE001
            err = str(exc).lower()
            is_rate_limit = "rate limit" in err or "429" in err or "rate_limit_exceeded" in err
            logger.warning("ConversationAgent LLM fallback activated: %s", exc)
            fallback_response = (
                "I'm briefly at capacity right now due to high AI traffic. Please try again in a few minutes."
                if is_rate_limit
                else "I ran into a temporary AI issue. Please try again in a moment."
            )
            llm_out = _LLMOutput(
                response=fallback_response,
                stage=stage,
                lead_profile_updates={},
                consent_requested=consent_requested,
                consent_given=consent_given,
                analytics_only=analytics_only,
            )

        # Merge updates with PDPL consent gating.
        updates = _normalize_updates(llm_out.lead_profile_updates)
        updates.update(_heuristic_updates_from_text(user_message))
        updates = _filter_allowed_lead_update_fields(updates)
        updates = _drop_empty_values(updates)
        if _has_uncertain_buy_intent(user_message):
            updates["intent"] = LeadIntent.unknown.value
        if _has_owner_seller_intent(user_message):
            updates["intent"] = LeadIntent.seller
        llm_consent_given = bool(llm_out.consent_given)
        llm_consent_requested = bool(llm_out.consent_requested)

        # Intent lock behavior:
        # once seller intent is confirmed, keep it unless user explicitly changes.
        proposed_intent = updates.get("intent")
        if isinstance(proposed_intent, LeadIntent):
            proposed_intent_value = proposed_intent
        elif isinstance(proposed_intent, str) and proposed_intent in LeadIntent._value2member_map_:
            proposed_intent_value = LeadIntent(proposed_intent)
        else:
            proposed_intent_value = None

        existing_intent_raw = lead_profile.get("intent")
        if isinstance(existing_intent_raw, LeadIntent):
            existing_intent = existing_intent_raw
        elif isinstance(existing_intent_raw, str) and existing_intent_raw in LeadIntent._value2member_map_:
            existing_intent = LeadIntent(existing_intent_raw)
        else:
            existing_intent = LeadIntent.unknown

        seller_confirmed = _has_owner_seller_intent(user_message)

        # Intent locking:
        # Once the user indicates they want to sell/list/own, lock seller intent.
        if not intent_locked and seller_confirmed:
            intent_locked = True
            locked_intent = LeadIntent.seller
            updates["intent"] = LeadIntent.seller

        # Only unlock seller intent if the user explicitly switches to buying.
        if (
            intent_locked
            and locked_intent
            and proposed_intent_value
            and proposed_intent_value != locked_intent
        ):
            if _has_explicit_buy_override(user_message):
                intent_locked = False
                locked_intent = None
                # Prefer the proposed buy intent, but always keep it as a buyer-primary default.
                updates["intent"] = (
                    proposed_intent_value if proposed_intent_value != LeadIntent.seller else LeadIntent.buyer_primary
                )
            else:
                updates["intent"] = locked_intent

        if llm_consent_given and not consent_given:
            consent_just_granted = True
        consent_given = consent_given or llm_consent_given

        if consent_just_granted:
            now = datetime.now(timezone.utc)
            updates["consent_given"] = True
            updates["consent_timestamp"] = now
            lead_profile["consent_given"] = True
            lead_profile["consent_timestamp"] = now

        state_updates = dict(updates)

        # Apply state-safe updates.
        lead_profile.update({k: v for k, v in state_updates.items() if v is not None})

        # Update state flags.
        consent_requested = consent_requested or llm_consent_requested
        analytics_only = analytics_only or bool(llm_out.analytics_only)

        # Stage progression rules:
        next_stage = llm_out.stage

        # Force completion guard for long loops.
        force_consent_now = turn_count >= 12 and not consent_given

        # If we have enough details, move to CONSENT unless analytics-only.
        if next_stage in {
            ConversationStage.GREETING,
            ConversationStage.INTENT_DISCOVERY,
            ConversationStage.DETAILS_COLLECTION,
            ConversationStage.PERSONAL_INFO,
        }:
            if _is_complete(lead_profile, consent_given=False, analytics_only=True) and not analytics_only:
                next_stage = ConversationStage.PERSONAL_INFO

        # If consent denied, proceed to SUMMARY in analytics-only mode.
        if analytics_only and next_stage == ConversationStage.CONSENT:
            next_stage = ConversationStage.SUMMARY

        # Once explicit consent is granted, complete intake and trigger pipeline.
        if consent_just_granted:
            next_stage = ConversationStage.SUMMARY

        intent_for_flow_raw = lead_profile.get("intent", LeadIntent.unknown)
        if isinstance(intent_for_flow_raw, LeadIntent):
            intent_for_flow = intent_for_flow_raw
        elif isinstance(intent_for_flow_raw, str) and intent_for_flow_raw in LeadIntent._value2member_map_:
            intent_for_flow = LeadIntent(intent_for_flow_raw)
        else:
            intent_for_flow = LeadIntent.unknown

        missing_fields = _missing_fields_for_flow(
            lead_profile=lead_profile,
            intent=intent_for_flow,
            consent_given=consent_given,
        )
        if force_consent_now:
            consent_requested = True
            next_stage = ConversationStage.CONSENT

        # Required PERSONAL_INFO gate before CONSENT:
        # full_name AND (email OR phone) must be captured.
        if next_stage == ConversationStage.CONSENT and not consent_given:
            if not _is_field_present(lead_profile.get("full_name")):
                response_text = "Before I save your details, could I get your name?"
                next_stage = ConversationStage.PERSONAL_INFO
                consent_requested = False
            elif not _is_field_present(lead_profile.get("email")) and not _is_field_present(
                lead_profile.get("phone")
            ):
                response_text = "And what's the best way to reach you - email or phone number?"
                next_stage = ConversationStage.PERSONAL_INFO
                consent_requested = False

        # If details are complete but personal info is missing, stay in PERSONAL_INFO.
        if (
            next_stage != ConversationStage.CONSENT
            and not consent_given
            and _is_complete(lead_profile, consent_given=False, analytics_only=True)
            and not _has_required_personal_info(lead_profile)
        ):
            next_stage = ConversationStage.PERSONAL_INFO
            response_text = (
                "Great! Before we connect you with an agent, could I get your preferred name and the "
                "best email or phone to reach you at?"
            )

        # If complete (with consent or analytics-only), go to SUMMARY.
        is_complete = consent_just_granted or _is_complete(
            lead_profile, consent_given=consent_given, analytics_only=analytics_only
        )
        if intent_for_flow == LeadIntent.seller:
            # Seller flow completion: no buyer-style requirements.
            seller_ready = (
                not any(
                    field in missing_fields
                    for field in (
                        "property_type",
                        "preferred_locations",
                        "asking_price_or_rent",
                        "timeline",
                        "consent",
                    )
                )
                and consent_given
            )
            is_complete = is_complete or seller_ready
        if is_complete:
            next_stage = ConversationStage.SUMMARY

        response_text = llm_out.response
        if force_consent_now and not consent_given:
            known_bits: list[str] = []
            if lead_profile.get("intent"):
                known_bits.append(f"Intent: {lead_profile.get('intent')}")
            if lead_profile.get("property_type"):
                known_bits.append(f"Property: {lead_profile.get('property_type')}")
            if lead_profile.get("preferred_locations"):
                known_bits.append(f"Location: {', '.join(lead_profile.get('preferred_locations') or [])}")
            if lead_profile.get("budget_min") or lead_profile.get("budget_max"):
                known_bits.append(
                    "Asking price/rent: "
                    + f"${lead_profile.get('budget_min') or ''}-{lead_profile.get('budget_max') or ''}".strip("-")
                )
            if lead_profile.get("timeline"):
                known_bits.append(f"Timeline: {lead_profile.get('timeline')}")
            summary = "; ".join([b for b in known_bits if b])
            response_text = (
                (f"Quick summary so far: {summary}. " if summary else "Quick summary so far. ")
                + "Before I save your details so an agent can reach out, I need your permission. Is that okay?"
            )
        elif next_stage == ConversationStage.CONSENT and not consent_given and "permission" not in response_text.lower():
            response_text = (
                "Before I save your details so an agent can reach out, I need your permission. Is that okay?"
            )

        # Seller-specific deterministic question flow:
        # Ask ONLY seller/landlord questions in this order, skipping any fields already filled.
        if intent_for_flow == LeadIntent.seller and not consent_given and not force_consent_now:
            sub_intent = lead_profile.get("sub_intent")
            is_landlord = sub_intent == "landlord"

            def _timeline_is_meaningful() -> bool:
                val = lead_profile.get("timeline")
                if val is None:
                    return False
                if val == LeadTimeline.exploring:
                    return False
                if isinstance(val, str):
                    try:
                        return LeadTimeline(val) != LeadTimeline.exploring
                    except Exception:
                        return True
                return True

            # a) Property type
            if not _is_field_present(lead_profile.get("property_type")):
                response_text = (
                    "What type of property is it (house, condo, townhouse, multi-family, etc.)?"
                )
                next_stage = ConversationStage.DETAILS_COLLECTION
            # b) Location
            elif not _is_field_present(lead_profile.get("preferred_locations")) and not _is_field_present(
                lead_profile.get("target_market")
            ):
                response_text = (
                    "What location is the property in (city + neighborhood, or nearby area/address)?"
                )
                next_stage = ConversationStage.DETAILS_COLLECTION
            # c) Estimated value / asking price (or asking rent for landlords)
            elif not (_is_field_present(lead_profile.get("budget_min")) or _is_field_present(lead_profile.get("budget_max"))):
                response_text = (
                    "What is your estimated value or asking price for the property?"
                    if not is_landlord
                    else "What asking rent are you targeting (or your estimated rent range per month)?"
                )
                next_stage = ConversationStage.DETAILS_COLLECTION
            # d) Timeline to sell / rent out
            elif not _timeline_is_meaningful():
                response_text = (
                    "When are you hoping to sell?"
                    if not is_landlord
                    else "When are you hoping to have it rented out / find tenants?"
                )
                next_stage = ConversationStage.DETAILS_COLLECTION
            # e) Specific requirements (proxy via financing_type)
            elif lead_profile.get("financing_type") is None or lead_profile.get("financing_type") == FinancingType.unknown:
                response_text = (
                    "Do you have any requirements for tenants (e.g., income range, credit/profile, pets, or flexible terms)?"
                    if is_landlord
                    else "Do you have any requirements for the buyer (e.g., cash buyer only, FHA/VA ok, first-time buyer ok)?"
                )
                next_stage = ConversationStage.DETAILS_COLLECTION
            # f) Contact info then consent
            else:
                if not _is_field_present(lead_profile.get("full_name")):
                    response_text = "Who am I speaking with today?"
                    next_stage = ConversationStage.PERSONAL_INFO
                    consent_requested = False
                elif not _is_field_present(lead_profile.get("email")) and not _is_field_present(
                    lead_profile.get("phone")
                ):
                    response_text = (
                        "Great! Before we connect you with an agent, could I get your preferred name and the "
                        "best email or phone to reach you at?"
                    )
                    next_stage = ConversationStage.PERSONAL_INFO
                    consent_requested = False
                else:
                    response_text = (
                        "Before I save your details so an agent can reach out, I need your permission. Is that okay?"
                    )
                    next_stage = ConversationStage.CONSENT
                    consent_requested = True

        # Persist assistant response to transcript table (PII redacted).
        if db is not None and session_id:
            db.add(
                ConversationTranscriptORM(
                    session_id=session_id,
                    lead_id=None,
                    role=ChatRole.assistant,
                    content=_redact_transcript_pii(response_text),
                    timestamp=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        result = AgentTurnResult(
            response=response_text,
            lead_profile_updates=updates,
            stage=next_stage.value,
            is_complete=is_complete,
            consent_requested=consent_requested,
            consent_given=consent_given,
            widget=_build_widget_for_turn(
                previous_stage=stage,
                response_text=response_text,
                missing_fields=missing_fields,
            ),
        )

        new_state: ConversationState = {
            "stage": next_stage.value,
            "lead_profile": lead_profile,
            "consent_given": consent_given,
            "consent_requested": consent_requested,
            "analytics_only": analytics_only,
            "turn_count": turn_count,
            "intent_locked": intent_locked,
        }
        if locked_intent is not None:
            new_state["locked_intent"] = locked_intent.value

        return result, new_state


