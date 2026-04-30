"""
Routing Agent

Routes leads after compliance checks, persists records with audit trail,
detects duplicates, and pushes hot compliant leads to Google Sheets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.schemas import (
    ComplianceResult,
    ComplianceResultORM,
    IntentResult,
    IntentResultORM,
    LeadProfile,
    LeadProfileORM,
    ScoreBucket,
    ScoreResult,
    ScoreResultORM,
)
from ..services.notification_service import NotificationService
from ..services.sheets_service import SheetsService


class RoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routed: bool
    destination: str
    reason: str
    timestamp: datetime
    suggested_agent_market: Optional[str] = None


class RoutingAgent:
    """Compliance-gated lead routing agent."""

    def __init__(
        self,
        sheets_service: Optional[SheetsService] = None,
        notification_service: Optional[NotificationService] = None,
    ) -> None:
        self.sheets_service = sheets_service
        self.notification_service = notification_service or NotificationService()

    @staticmethod
    def _suggested_agent_market(lead_profile: LeadProfile) -> Optional[str]:
        if lead_profile.target_market and lead_profile.target_market.strip():
            return lead_profile.target_market.strip()
        if lead_profile.preferred_locations:
            return lead_profile.preferred_locations[0]
        return None

    @staticmethod
    def _budget_range_str(lead_profile: LeadProfile) -> str:
        lo = lead_profile.budget_min
        hi = lead_profile.budget_max
        if lo is not None and hi is not None:
            return f"${lo:,.0f} - ${hi:,.0f}"
        if lo is not None:
            return f"${lo:,.0f}+"
        if hi is not None:
            return f"Up to ${hi:,.0f}"
        return "N/A"

    @staticmethod
    def _preapproval_status(score_result: ScoreResult) -> str:
        joined = " ".join(score_result.signals).lower()
        if "pre-approved" in joined or "pre approved" in joined:
            return "Pre-approved"
        if "pre-qualified" in joined or "pre qualified" in joined:
            return "Pre-qualified"
        if "talked to a lender" in joined or "spoke to a lender" in joined:
            return "Talked to lender"
        if "cash buyer" in joined:
            return "Cash buyer"
        return "Unknown"

    async def _find_duplicate(
        self,
        db: AsyncSession,
        lead_profile: LeadProfile,
    ) -> Optional[LeadProfileORM]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        filters = []
        if lead_profile.email:
            filters.append(LeadProfileORM.email == lead_profile.email)
        if lead_profile.phone:
            filters.append(LeadProfileORM.phone == lead_profile.phone)
        if not filters:
            return None

        query = (
            select(LeadProfileORM)
            .where(or_(*filters))
            .where(LeadProfileORM.created_at >= cutoff)
            .order_by(LeadProfileORM.created_at.desc())
            .limit(1)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _upsert_lead_with_audit(
        self,
        db: AsyncSession,
        lead_profile: LeadProfile,
        intent_result: IntentResult,
        score_result: ScoreResult,
        compliance_result: ComplianceResult,
    ) -> LeadProfileORM:
        existing = await self._find_duplicate(db, lead_profile)
        now = datetime.now(timezone.utc)

        if existing:
            existing.full_name = lead_profile.full_name
            existing.email = lead_profile.email
            existing.phone = lead_profile.phone
            existing.intent = lead_profile.intent
            existing.budget_min = lead_profile.budget_min
            existing.budget_max = lead_profile.budget_max
            existing.target_market = lead_profile.target_market
            existing.preferred_locations = lead_profile.preferred_locations
            existing.timeline = lead_profile.timeline
            existing.property_type = lead_profile.property_type
            existing.financing_type = lead_profile.financing_type
            existing.is_first_time_buyer = lead_profile.is_first_time_buyer
            existing.consent_given = lead_profile.consent_given
            existing.consent_timestamp = lead_profile.consent_timestamp
            existing.source = lead_profile.source
            existing.updated_at = now
            lead_row = existing
        else:
            lead_row = LeadProfileORM(
                id=lead_profile.id,
                full_name=lead_profile.full_name,
                email=lead_profile.email,
                phone=lead_profile.phone,
                intent=lead_profile.intent,
                budget_min=lead_profile.budget_min,
                budget_max=lead_profile.budget_max,
                target_market=lead_profile.target_market,
                preferred_locations=lead_profile.preferred_locations,
                timeline=lead_profile.timeline,
                property_type=lead_profile.property_type,
                financing_type=lead_profile.financing_type,
                is_first_time_buyer=lead_profile.is_first_time_buyer,
                consent_given=lead_profile.consent_given,
                consent_timestamp=lead_profile.consent_timestamp,
                source=lead_profile.source,
                created_at=lead_profile.created_at,
                updated_at=lead_profile.updated_at,
            )
            db.add(lead_row)
            await db.flush()

        # Audit trail: persist all derived agent outputs as immutable rows.
        db.add(
            IntentResultORM(
                lead_id=lead_row.id,
                classification=intent_result.classification,
                confidence=intent_result.confidence,
                rationale=intent_result.rationale,
                timestamp=intent_result.timestamp,
            )
        )
        db.add(
            ScoreResultORM(
                lead_id=lead_row.id,
                heat_score=score_result.heat_score,
                bucket=score_result.bucket,
                signals=score_result.signals,
                timestamp=score_result.timestamp,
            )
        )
        db.add(
            ComplianceResultORM(
                lead_id=lead_row.id,
                consent_verified=compliance_result.consent_verified,
                pii_redacted=compliance_result.pii_redacted,
                blocked_claims=compliance_result.blocked_claims,
                sanitized_transcript=compliance_result.sanitized_transcript,
                compliant=compliance_result.compliant,
                timestamp=compliance_result.timestamp,
            )
        )
        await db.commit()
        await db.refresh(lead_row)
        return lead_row

    async def route(
        self,
        db: AsyncSession,
        lead_profile: LeadProfile,
        intent_result: IntentResult,
        score_result: ScoreResult,
        compliance_result: ComplianceResult,
    ) -> RoutingResult:
        """
        Execute routing flow:
        1) Compliance gate
        2) Store lead + audit trail
        3) Route hot, compliant leads to Google Sheets
        4) Duplicate detection handled on store (update existing)
        5) Add suggested geographic market assignment metadata
        """
        suggested_market = self._suggested_agent_market(lead_profile)

        # Always store with audit trail (including blocked leads).
        lead_row = await self._upsert_lead_with_audit(
            db=db,
            lead_profile=lead_profile,
            intent_result=intent_result,
            score_result=score_result,
            compliance_result=compliance_result,
        )

        # Compliance gate
        if not compliance_result.compliant:
            reason = (
                "Blocked by compliance gate. "
                + ("; ".join(compliance_result.blocked_claims) if compliance_result.blocked_claims else "No details provided.")
            )
            return RoutingResult(
                routed=False,
                destination="blocked",
                reason=reason,
                timestamp=datetime.now(timezone.utc),
                suggested_agent_market=suggested_market,
            )

        # Route hot leads to Sheets
        if score_result.bucket == ScoreBucket.hot:
            if self.sheets_service is None:
                self.sheets_service = SheetsService()
            row = [
                lead_row.full_name or "",
                lead_row.email or "",
                lead_row.phone or "",
                intent_result.classification.value,
                str(score_result.heat_score),
                self._budget_range_str(lead_profile),
                ", ".join(lead_profile.preferred_locations) or (lead_profile.target_market or ""),
                lead_profile.timeline.value,
                lead_profile.financing_type.value,
                "Y" if lead_profile.is_first_time_buyer else "N",
                self._preapproval_status(score_result),
                datetime.now(timezone.utc).isoformat(),
                suggested_market or "",
            ]
            await self.sheets_service.append_row(row)
            await self.notification_service.notify_hot_lead_routed(
                db=db,
                lead_id=lead_row.id,
                lead_name=lead_row.full_name,
                intent=intent_result.classification,
                score=score_result.heat_score,
                budget_summary=self._budget_range_str(lead_profile),
                market=", ".join(lead_profile.preferred_locations) or (lead_profile.target_market or "N/A"),
                timeline=lead_profile.timeline.value,
                destination="google_sheets",
            )
            return RoutingResult(
                routed=True,
                destination="google_sheets",
                reason="Hot compliant lead routed immediately to sales sheet.",
                timestamp=datetime.now(timezone.utc),
                suggested_agent_market=suggested_market,
            )

        # Warm/cold: stored only
        return RoutingResult(
            routed=False,
            destination="stored",
            reason="Lead stored with full audit trail; not hot enough for immediate routing.",
            timestamp=datetime.now(timezone.utc),
            suggested_agent_market=suggested_market,
        )


