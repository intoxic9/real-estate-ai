"""
Clay and CSV lead import service.

Imports enriched leads and runs them through scoring + routing
without using the Conversation Agent.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agents.routing_agent import RoutingAgent, RoutingResult
from ..agents.scoring_agent import ScoringAgent
from ..core.schemas import (
    ComplianceResult,
    FinancingType,
    IntentResult,
    LeadIntent,
    LeadProfile,
    LeadTimeline,
    PropertyType,
)


class ClayService:
    def __init__(self) -> None:
        self.clay_api_key = os.getenv("CLAY_API_KEY", "").strip()
        self.webhook_secret = os.getenv("CLAY_WEBHOOK_SECRET", "").strip()
        self.scoring_agent = ScoringAgent()
        self.routing_agent = RoutingAgent()

    @staticmethod
    def _parse_bool(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "yes", "y", "1"}:
                return True
            if v in {"false", "no", "n", "0"}:
                return False
        return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if cleaned == "":
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_locations(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [x.strip() for x in value.split(",") if x.strip()]
        return []

    @staticmethod
    def _map_intent(value: Any) -> LeadIntent:
        raw = str(value or "").strip().lower()
        mapping = {
            "buyer_primary": LeadIntent.buyer_primary,
            "buyer": LeadIntent.buyer_primary,
            "buyer_investment": LeadIntent.buyer_investment,
            "investor": LeadIntent.buyer_investment,
            "seller": LeadIntent.seller,
            "renter": LeadIntent.renter,
            "refinance": LeadIntent.refinance,
        }
        return mapping.get(raw, LeadIntent.unknown)

    @staticmethod
    def _map_timeline(value: Any) -> LeadTimeline:
        raw = str(value or "").strip().lower()
        mapping = {
            "immediate": LeadTimeline.immediate,
            "1_3_months": LeadTimeline.one_to_three_months,
            "one_to_three_months": LeadTimeline.one_to_three_months,
            "3_6_months": LeadTimeline.three_to_six_months,
            "three_to_six_months": LeadTimeline.three_to_six_months,
            "6_12_months": LeadTimeline.six_to_twelve_months,
            "six_to_twelve_months": LeadTimeline.six_to_twelve_months,
            "exploring": LeadTimeline.exploring,
        }
        return mapping.get(raw, LeadTimeline.exploring)

    @staticmethod
    def _map_property_type(value: Any) -> PropertyType:
        raw = str(value or "").strip().lower()
        mapping = {
            "single_family": PropertyType.single_family,
            "single family": PropertyType.single_family,
            "apartment": PropertyType.apartment,
            "villa": PropertyType.villa,
            "townhouse": PropertyType.townhouse,
            "penthouse": PropertyType.penthouse,
            "commercial": PropertyType.commercial,
            "land": PropertyType.land,
        }
        return mapping.get(raw, PropertyType.apartment)

    @staticmethod
    def _map_financing_type(value: Any) -> FinancingType:
        raw = str(value or "").strip().lower()
        mapping = {
            "cash": FinancingType.cash,
            "conventional": FinancingType.conventional,
            "fha": FinancingType.fha,
            "va": FinancingType.va,
            "other": FinancingType.other,
        }
        return mapping.get(raw, FinancingType.unknown)

    def map_payload_to_lead_profile(self, payload: Dict[str, Any], source: str) -> LeadProfile:
        now = datetime.now(timezone.utc)
        locations = self._parse_locations(
            payload.get("preferred_locations")
            or payload.get("locations")
            or payload.get("target_locations")
        )
        consent_given = self._parse_bool(payload.get("consent_given"))
        if consent_given is None:
            consent_given = False
        consent_ts = now if consent_given else None

        return LeadProfile(
            full_name=payload.get("full_name") or payload.get("name"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            intent=self._map_intent(payload.get("intent")),
            budget_min=self._parse_float(payload.get("budget_min") or payload.get("min_budget")),
            budget_max=self._parse_float(payload.get("budget_max") or payload.get("max_budget")),
            target_market=payload.get("target_market") or payload.get("market"),
            preferred_locations=locations,
            timeline=self._map_timeline(payload.get("timeline")),
            property_type=self._map_property_type(payload.get("property_type")),
            financing_type=self._map_financing_type(payload.get("financing_type")),
            is_first_time_buyer=self._parse_bool(payload.get("is_first_time_buyer")),
            consent_given=consent_given,
            consent_timestamp=consent_ts,
            source=source,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _build_intent_result(lead: LeadProfile) -> IntentResult:
        confidence = 0.8 if lead.intent != LeadIntent.unknown else 0.5
        rationale = ["Imported enriched lead intent from upstream source."]
        return IntentResult(
            lead_id=lead.id,
            classification=lead.intent if lead.intent != LeadIntent.unknown else LeadIntent.buyer_primary,
            confidence=confidence,
            rationale=rationale,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _build_compliance_result(lead: LeadProfile, raw_context: str) -> ComplianceResult:
        consent_verified = bool(lead.consent_given and lead.consent_timestamp is not None)
        blocked_claims: List[str] = []
        if not consent_verified:
            blocked_claims.append("CONSENT_MISSING_OR_INCOMPLETE: Imported lead missing consent.")
        return ComplianceResult(
            lead_id=lead.id,
            consent_verified=consent_verified,
            pii_redacted=False,
            blocked_claims=blocked_claims,
            sanitized_transcript=f"import_context: {raw_context[:2000]}",
            compliant=consent_verified and len(blocked_claims) == 0,
            timestamp=datetime.now(timezone.utc),
        )

    async def process_imported_lead(
        self,
        db: Any,
        lead_profile: LeadProfile,
        raw_context: str,
    ) -> Dict[str, Any]:
        intent_result = self._build_intent_result(lead_profile)
        score_result = await self.scoring_agent.score(
            lead_profile=lead_profile,
            intent_result=intent_result,
            transcript=raw_context,
        )
        compliance_result = self._build_compliance_result(lead_profile, raw_context)
        routing_result: RoutingResult = await self.routing_agent.route(
            db=db,
            lead_profile=lead_profile,
            intent_result=intent_result,
            score_result=score_result,
            compliance_result=compliance_result,
        )
        return {
            "lead_id": str(lead_profile.id),
            "score": score_result.heat_score,
            "bucket": score_result.bucket.value,
            "routed": routing_result.routed,
            "destination": routing_result.destination,
            "reason": routing_result.reason,
        }

    async def import_from_clay_payload(
        self,
        db: Any,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        lead = self.map_payload_to_lead_profile(payload, source="clay")
        return await self.process_imported_lead(
            db=db,
            lead_profile=lead,
            raw_context=str(payload),
        )

    async def import_from_csv_bytes(self, db: Any, content: bytes) -> Dict[str, Any]:
        decoded = content.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(decoded))
        imported: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        for idx, row in enumerate(reader, start=1):
            try:
                lead = self.map_payload_to_lead_profile(dict(row), source="csv_import")
                result = await self.process_imported_lead(
                    db=db,
                    lead_profile=lead,
                    raw_context=str(row),
                )
                imported.append(result)
            except Exception as exc:  # noqa: BLE001
                failed.append({"row": str(idx), "error": str(exc)})
        return {
            "imported_count": len(imported),
            "failed_count": len(failed),
            "imported": imported,
            "failed": failed,
        }

