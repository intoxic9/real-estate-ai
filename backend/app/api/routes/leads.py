"""
Lead management API routes.

These handlers currently return mock data while exposing the intended
request/response contracts and using the database session dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import (
    ChatMessage,
    ChatMessageORM,
    ChatRole,
    ComplianceResult,
    ComplianceResultORM,
    ConversationTranscriptORM,
    FinancingType,
    LeadIntent,
    LeadProfile,
    LeadProfileORM,
    ScoreBucket,
    ScoreResult,
    ScoreResultORM,
)
from ...services.clay_service import ClayService
from ...services.sheets_service import SheetsService


router = APIRouter(prefix="/api/leads", tags=["leads"])
clay_service = ClayService()


class LeadListQueryParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    bucket: Optional[ScoreBucket] = None
    intent: Optional[LeadIntent] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class LeadListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead: LeadProfile
    latest_score: Optional[ScoreResult] = None
    latest_compliance: Optional[ComplianceResult] = None


class LeadListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[LeadListItem]
    total: int
    page: int
    page_size: int


class LeadDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead: LeadProfile
    scores: List[ScoreResult]
    compliance_results: List[ComplianceResult]
    transcript: List[ChatMessage]


class LeadUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    intent: Optional[LeadIntent] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    target_market: Optional[str] = None
    preferred_locations: Optional[List[str]] = None
    financing_type: Optional[FinancingType] = None
    is_first_time_buyer: Optional[bool] = None


class RouteLeadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    destination: str
    details: Optional[str] = None
    error: Optional[str] = None


class MarkComplianceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    lead_id: str
    details: Optional[str] = None
    error: Optional[str] = None


class ImportClayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: str
    score: int
    bucket: str
    routed: bool
    destination: str
    reason: str


class ImportCsvResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imported_count: int
    failed_count: int
    imported: List[dict[str, Any]]
    failed: List[dict[str, str]]


@router.get(
    "",
    response_model=LeadListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    bucket: Optional[ScoreBucket] = Query(default=None),
    intent: Optional[LeadIntent] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> LeadListResponse:
    """
    List leads with basic filtering and pagination.
    """
    _ = LeadListQueryParams(
        page=page,
        page_size=page_size,
        bucket=bucket,
        intent=intent,
        date_from=date_from,
        date_to=date_to,
    )

    query = select(LeadProfileORM)
    if intent is not None:
        query = query.where(LeadProfileORM.intent == intent)
    if date_from is not None:
        query = query.where(LeadProfileORM.created_at >= date_from)
    if date_to is not None:
        query = query.where(LeadProfileORM.created_at <= date_to)

    lead_rows = (
        await db.execute(
            query.order_by(LeadProfileORM.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    total = (await db.execute(query.with_only_columns(LeadProfileORM.id))).scalars().all()
    total_count = len(total)

    items: List[LeadListItem] = []
    for lead_row in lead_rows:
        latest_score_row = (
            await db.execute(
                select(ScoreResultORM)
                .where(ScoreResultORM.lead_id == lead_row.id)
                .order_by(ScoreResultORM.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if bucket is not None and (
            latest_score_row is None or latest_score_row.bucket != bucket
        ):
            continue

        latest_compliance_row = (
            await db.execute(
                select(ComplianceResultORM)
                .where(ComplianceResultORM.lead_id == lead_row.id)
                .order_by(ComplianceResultORM.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        lead = LeadProfile(
            id=lead_row.id,
            full_name=lead_row.full_name,
            email=lead_row.email,
            phone=lead_row.phone,
            intent=lead_row.intent,
            budget_min=lead_row.budget_min,
            budget_max=lead_row.budget_max,
            target_market=lead_row.target_market,
            preferred_locations=list(lead_row.preferred_locations or []),
            timeline=lead_row.timeline,
            property_type=lead_row.property_type,
            financing_type=lead_row.financing_type,
            is_first_time_buyer=lead_row.is_first_time_buyer,
            consent_given=lead_row.consent_given,
            consent_timestamp=lead_row.consent_timestamp,
            source=lead_row.source,
            created_at=lead_row.created_at,
            updated_at=lead_row.updated_at,
        )

        latest_score = (
            ScoreResult(
                lead_id=latest_score_row.lead_id,
                heat_score=latest_score_row.heat_score,
                bucket=latest_score_row.bucket,
                signals=list(latest_score_row.signals or []),
                timestamp=latest_score_row.timestamp,
            )
            if latest_score_row is not None
            else None
        )

        latest_compliance = (
            ComplianceResult(
                lead_id=latest_compliance_row.lead_id,
                consent_verified=latest_compliance_row.consent_verified,
                pii_redacted=latest_compliance_row.pii_redacted,
                blocked_claims=list(latest_compliance_row.blocked_claims or []),
                sanitized_transcript=latest_compliance_row.sanitized_transcript,
                compliant=latest_compliance_row.compliant,
                timestamp=latest_compliance_row.timestamp,
            )
            if latest_compliance_row is not None
            else None
        )

        items.append(
            LeadListItem(
                lead=lead,
                latest_score=latest_score,
                latest_compliance=latest_compliance,
            )
        )

    return LeadListResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{lead_id}",
    response_model=LeadDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_lead_detail(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
) -> LeadDetailResponse:
    """
    Return full lead detail including scores, compliance results, and transcript.
    """
    lead_uuid: Optional[UUID] = None
    try:
        lead_uuid = UUID(lead_id)
    except ValueError:
        lead_uuid = None

    lead_row = None
    if lead_uuid is not None:
        lead_row = (
            await db.execute(select(LeadProfileORM).where(LeadProfileORM.id == lead_uuid))
        ).scalar_one_or_none()
    if lead_row is None:
        now = datetime.now(timezone.utc)
        fallback_lead = LeadProfile(
            id=lead_id,  # type: ignore[arg-type]
            full_name=None,
            email=None,
            phone=None,
            property_type="apartment",  # type: ignore[arg-type]
            source="chatbot",
            created_at=now,
            updated_at=now,
        )
        return LeadDetailResponse(
            lead=fallback_lead,
            scores=[],
            compliance_results=[],
            transcript=[],
        )

    score_rows = (
        await db.execute(
            select(ScoreResultORM)
            .where(ScoreResultORM.lead_id == lead_uuid)
            .order_by(ScoreResultORM.timestamp.desc())
        )
    ).scalars().all()

    compliance_rows = (
        await db.execute(
            select(ComplianceResultORM)
            .where(ComplianceResultORM.lead_id == lead_uuid)
            .order_by(ComplianceResultORM.timestamp.desc())
        )
    ).scalars().all()

    # Pull the session_id for this lead so we can return a full transcript for that session.
    session_id = (
        await db.execute(
            select(ConversationTranscriptORM.session_id)
            .where(ConversationTranscriptORM.lead_id == lead_uuid)
            .limit(1)
        )
    ).scalar_one_or_none()

    transcript_rows = (
        await db.execute(
            select(ConversationTranscriptORM)
            .where(
                ConversationTranscriptORM.session_id == session_id
                if session_id is not None
                else (ConversationTranscriptORM.lead_id == lead_uuid)
            )
            .order_by(ConversationTranscriptORM.timestamp.asc(), ConversationTranscriptORM.id.asc())
        )
    ).scalars().all()

    # Backwards compatibility: some environments may still have transcripts stored
    # in the legacy `chat_messages` table (lead_id-based).
    chat_rows: list[Any] = []
    if not transcript_rows:
        chat_rows = (
            await db.execute(
                select(ChatMessageORM)
                .where(ChatMessageORM.lead_id == lead_uuid)
                .order_by(ChatMessageORM.timestamp.asc(), ChatMessageORM.id.asc())
            )
        ).scalars().all()

    lead = LeadProfile(
        id=lead_row.id,
        full_name=lead_row.full_name,
        email=lead_row.email,
        phone=lead_row.phone,
        intent=lead_row.intent,
        budget_min=lead_row.budget_min,
        budget_max=lead_row.budget_max,
        target_market=lead_row.target_market,
        preferred_locations=list(lead_row.preferred_locations or []),
        timeline=lead_row.timeline,
        property_type=lead_row.property_type,
        financing_type=lead_row.financing_type,
        is_first_time_buyer=lead_row.is_first_time_buyer,
        consent_given=lead_row.consent_given,
        consent_timestamp=lead_row.consent_timestamp,
        source=lead_row.source,
        created_at=lead_row.created_at,
        updated_at=lead_row.updated_at,
    )
    scores = [
        ScoreResult(
            lead_id=row.lead_id,
            heat_score=row.heat_score,
            bucket=row.bucket,
            signals=list(row.signals or []),
            timestamp=row.timestamp,
        )
        for row in score_rows
    ]
    compliance_results = [
        ComplianceResult(
            lead_id=row.lead_id,
            consent_verified=row.consent_verified,
            pii_redacted=row.pii_redacted,
            blocked_claims=list(row.blocked_claims or []),
            sanitized_transcript=row.sanitized_transcript,
            compliant=row.compliant,
            timestamp=row.timestamp,
        )
        for row in compliance_rows
    ]
    if transcript_rows:
        transcript = [
            ChatMessage(
                role=row.role if isinstance(row.role, ChatRole) else ChatRole(str(row.role)),
                content=row.content,
                timestamp=row.timestamp,
                metadata=None,
            )
            for row in transcript_rows
        ]
    else:
        transcript = [
            ChatMessage(
                role=row.role if isinstance(row.role, ChatRole) else ChatRole(str(row.role)),
                content=row.content,
                timestamp=row.timestamp,
                metadata=row.extra_metadata,
            )
            for row in chat_rows
        ]

    return LeadDetailResponse(
        lead=lead,
        scores=scores,
        compliance_results=compliance_results,
        transcript=transcript,
    )


@router.put(
    "/{lead_id}",
    response_model=LeadProfile,
    status_code=status.HTTP_200_OK,
)
async def update_lead(
    lead_id: str,
    payload: LeadUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> LeadProfile:
    """
    Update lead information. Currently returns a mock updated lead.
    """

    _ = db
    now = datetime.now(timezone.utc)

    lead = LeadProfile(
        id=lead_id,  # type: ignore[arg-type]
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        intent=payload.intent or "buyer",  # type: ignore[arg-type]
        property_type="apartment",  # type: ignore[arg-type]
        budget_min=payload.budget_min,
        budget_max=payload.budget_max,
        target_market=payload.target_market,
        preferred_locations=payload.preferred_locations or [],
        financing_type=payload.financing_type or FinancingType.unknown,
        is_first_time_buyer=payload.is_first_time_buyer,
        source="chatbot",
        created_at=now,
        updated_at=now,
    )

    return lead


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_lead(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    PDPL-compliant deletion endpoint. For now this is a mock that
    validates the identifier and returns 204.
    """

    _ = db

    if not lead_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lead_id is required",
        )

    # TODO: Implement hard delete with audit logging via compliance service.
    return None


@router.post(
    "/{lead_id}/route",
    response_model=RouteLeadResponse,
    status_code=status.HTTP_200_OK,
)
async def route_lead(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
) -> RouteLeadResponse:
    """
    Manually trigger routing to Google Sheets CRM synchronously so
    routing errors are returned in the response.
    """

    if not lead_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lead_id is required",
        )

    try:
        lead_uuid = UUID(lead_id)
    except ValueError:
        return RouteLeadResponse(
            status="failed",
            destination="google_sheets",
            error="Invalid lead_id format.",
        )

    try:
        lead_row = (
            await db.execute(select(LeadProfileORM).where(LeadProfileORM.id == lead_uuid))
        ).scalar_one_or_none()
        if lead_row is None:
            return RouteLeadResponse(
                status="failed",
                destination="google_sheets",
                error="Lead not found.",
            )

        latest_score = (
            await db.execute(
                select(ScoreResultORM)
                .where(ScoreResultORM.lead_id == lead_uuid)
                .order_by(ScoreResultORM.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_score is None:
            return RouteLeadResponse(
                status="failed",
                destination="google_sheets",
                error="No score found for lead.",
            )

        latest_compliance = (
            await db.execute(
                select(ComplianceResultORM)
                .where(ComplianceResultORM.lead_id == lead_uuid)
                .order_by(ComplianceResultORM.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_compliance is None:
            return RouteLeadResponse(
                status="failed",
                destination="google_sheets",
                error="No compliance result found for lead.",
            )
        if not latest_compliance.compliant:
            return RouteLeadResponse(
                status="failed",
                destination="blocked",
                error="Lead is blocked by compliance.",
            )

        budget_summary = "N/A"
        if lead_row.budget_min is not None and lead_row.budget_max is not None:
            budget_summary = f"${lead_row.budget_min:,.0f} - ${lead_row.budget_max:,.0f}"
        elif lead_row.budget_min is not None:
            budget_summary = f"${lead_row.budget_min:,.0f}+"
        elif lead_row.budget_max is not None:
            budget_summary = f"Up to ${lead_row.budget_max:,.0f}"

        row = [
            lead_row.full_name or "",
            lead_row.email or "",
            lead_row.phone or "",
            lead_row.intent.value if hasattr(lead_row.intent, "value") else str(lead_row.intent or ""),
            str(latest_score.heat_score),
            budget_summary,
            ", ".join(lead_row.preferred_locations or []) or (lead_row.target_market or ""),
            lead_row.timeline.value if hasattr(lead_row.timeline, "value") else str(lead_row.timeline or ""),
            lead_row.financing_type.value if hasattr(lead_row.financing_type, "value") else str(lead_row.financing_type or ""),
            "Y" if lead_row.is_first_time_buyer else "N",
            datetime.now(timezone.utc).isoformat(),
            (lead_row.target_market or ""),
        ]

        sheets = SheetsService()
        await sheets.append_row(row)
        return RouteLeadResponse(
            status="routed",
            destination="google_sheets",
            details="Lead routed to Google Sheets successfully.",
        )
    except Exception as exc:  # noqa: BLE001
        return RouteLeadResponse(
            status="failed",
            destination="google_sheets",
            error=str(exc),
        )


@router.post(
    "/{lead_id}/compliance/mark-compliant",
    response_model=MarkComplianceResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_lead_compliant(
    lead_id: str,
    db: AsyncSession = Depends(get_db),
) -> MarkComplianceResponse:
    if not lead_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lead_id is required",
        )
    try:
        lead_uuid = UUID(lead_id)
    except ValueError:
        return MarkComplianceResponse(
            status="failed",
            lead_id=lead_id,
            error="Invalid lead_id format.",
        )

    latest_compliance = (
        await db.execute(
            select(ComplianceResultORM)
            .where(ComplianceResultORM.lead_id == lead_uuid)
            .order_by(ComplianceResultORM.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if latest_compliance is None:
        return MarkComplianceResponse(
            status="failed",
            lead_id=lead_id,
            error="No compliance record found for this lead.",
        )

    latest_compliance.compliant = True
    latest_compliance.blocked_claims = []
    await db.commit()

    return MarkComplianceResponse(
        status="updated",
        lead_id=lead_id,
        details="Lead compliance status changed to compliant.",
    )


@router.post(
    "/import/clay",
    response_model=ImportClayResponse,
    status_code=status.HTTP_200_OK,
)
async def import_clay_lead(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    x_clay_webhook_secret: Optional[str] = Header(default=None),
) -> ImportClayResponse:
    expected_secret = clay_service.webhook_secret
    if expected_secret and x_clay_webhook_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Clay webhook secret")
    result = await clay_service.import_from_clay_payload(db=db, payload=payload)
    return ImportClayResponse(**result)


@router.post(
    "/import/csv",
    response_model=ImportCsvResponse,
    status_code=status.HTTP_200_OK,
)
async def import_csv_leads(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ImportCsvResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is required")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .csv uploads are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded CSV is empty")
    result = await clay_service.import_from_csv_bytes(db=db, content=content)
    return ImportCsvResponse(**result)


__all__ = ["router"]

