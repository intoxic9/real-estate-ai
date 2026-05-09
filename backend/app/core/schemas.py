"""
Pydantic schemas and SQLAlchemy ORM models for the Dubai/UAE
real estate lead intelligence system.

The models are designed for PDPL compliance:
- Extra fields are forbidden on all Pydantic models.
- Enums are strict to prevent unexpected values.
- Scores and numeric fields use explicit bounds where applicable.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LeadIntent(str, enum.Enum):
    buyer_primary = "buyer_primary"
    buyer_investment = "buyer_investment"
    buyer = "buyer"
    seller = "seller"
    renter = "renter"
    refinance = "refinance"
    investor = "investor"
    unknown = "unknown"


class LeadTimeline(str, enum.Enum):
    immediate = "immediate"
    one_to_three_months = "1_3_months"
    three_to_six_months = "3_6_months"
    six_to_twelve_months = "6_12_months"
    exploring = "exploring"


class PropertyType(str, enum.Enum):
    single_family = "single_family"
    apartment = "apartment"
    villa = "villa"
    townhouse = "townhouse"
    penthouse = "penthouse"
    commercial = "commercial"
    land = "land"


class FinancingType(str, enum.Enum):
    cash = "cash"
    conventional = "conventional"
    fha = "fha"
    va = "va"
    other = "other"
    unknown = "unknown"


class ScoreBucket(str, enum.Enum):
    hot = "hot"
    warm = "warm"
    cold = "cold"


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class SignalSource(str, enum.Enum):
    reddit_api = "reddit_api"
    reddit_rss = "reddit_rss"
    twitter = "twitter"
    twitter_google = "twitter_google"
    google_alerts = "google_alerts"


class SignalIntentLevel(str, enum.Enum):
    strong_intent = "strong_intent"
    moderate_intent = "moderate_intent"
    weak_intent = "weak_intent"
    not_relevant = "not_relevant"


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class LeadProfileORM(Base):
    __tablename__ = "lead_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    intent: Mapped[LeadIntent] = mapped_column(
        SAEnum(LeadIntent, name="lead_intent_enum", native_enum=True),
        nullable=False,
        index=True,
        default=LeadIntent.unknown,
    )
    budget_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    budget_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_market: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    preferred_locations: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    timeline: Mapped[LeadTimeline] = mapped_column(
        SAEnum(LeadTimeline, name="lead_timeline_enum", native_enum=True),
        nullable=False,
        default=LeadTimeline.exploring,
    )
    property_type: Mapped[PropertyType] = mapped_column(
        SAEnum(PropertyType, name="property_type_enum", native_enum=True),
        nullable=False,
    )
    financing_type: Mapped[FinancingType] = mapped_column(
        SAEnum(FinancingType, name="financing_type_enum", native_enum=True),
        nullable=False,
        default=FinancingType.unknown,
    )
    is_first_time_buyer: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Relationships
    intent_results: Mapped[List["IntentResultORM"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    score_results: Mapped[List["ScoreResultORM"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    compliance_results: Mapped[List["ComplianceResultORM"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )
    chat_messages: Mapped[List["ChatMessageORM"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
    )


Index("idx_lead_profiles_intent_created_at", LeadProfileORM.intent, LeadProfileORM.created_at)


class IntentResultORM(Base):
    __tablename__ = "intent_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    classification: Mapped[LeadIntent] = mapped_column(
        SAEnum(LeadIntent, name="intent_classification_enum", native_enum=True),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    lead: Mapped[LeadProfileORM] = relationship(back_populates="intent_results")


class ScoreResultORM(Base):
    __tablename__ = "score_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    heat_score: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket: Mapped[ScoreBucket] = mapped_column(
        SAEnum(ScoreBucket, name="score_bucket_enum", native_enum=True),
        nullable=False,
    )
    signals: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    lead: Mapped[LeadProfileORM] = relationship(back_populates="score_results")


class ComplianceResultORM(Base):
    __tablename__ = "compliance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pii_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    blocked_claims: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    sanitized_transcript: Mapped[str] = mapped_column(
        String,  # TODO: Consider using a text type depending on DB.
        nullable=False,
    )
    compliant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    lead: Mapped[LeadProfileORM] = relationship(back_populates="compliance_results")


class MarketSnapshotORM(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    area: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    median_sale_price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_sqft_usd: Mapped[float] = mapped_column(Float, nullable=False)
    median_rent_usd: Mapped[float] = mapped_column(Float, nullable=False)
    days_on_market: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


Index(
    "idx_market_snapshots_area_date",
    MarketSnapshotORM.area,
    MarketSnapshotORM.snapshot_date,
)


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[ChatRole] = mapped_column(
        SAEnum(ChatRole, name="chat_role_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    # NOTE: attribute name cannot be "metadata" (reserved by SQLAlchemy),
    # so we use "extra_metadata" as the Python attribute while keeping
    # the underlying column name as "metadata" for clarity.
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    lead: Mapped[Optional[LeadProfileORM]] = relationship(back_populates="chat_messages")


class ConversationTranscriptORM(Base):
    __tablename__ = "conversation_transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[ChatRole] = mapped_column(
        SAEnum(ChatRole, name="conversation_transcript_role_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


Index(
    "idx_conversation_transcripts_session_ts",
    ConversationTranscriptORM.session_id,
    ConversationTranscriptORM.timestamp,
)


class LeadSignalORM(Base):
    __tablename__ = "lead_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source: Mapped[SignalSource] = mapped_column(
        SAEnum(SignalSource, name="signal_source_enum", native_enum=True),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    locations_mentioned: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    apparent_intent: Mapped[LeadIntent] = mapped_column(
        SAEnum(LeadIntent, name="signal_apparent_intent_enum", native_enum=True),
        nullable=False,
        default=LeadIntent.unknown,
    )
    intent_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent_level: Mapped[SignalIntentLevel] = mapped_column(
        SAEnum(SignalIntentLevel, name="signal_intent_level_enum", native_enum=True),
        nullable=False,
        default=SignalIntentLevel.not_relevant,
        index=True,
    )
    raw_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    converted_to_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    lead: Mapped[Optional[LeadProfileORM]] = relationship()


Index(
    "idx_lead_signals_source_intent_level_captured",
    LeadSignalORM.source,
    LeadSignalORM.intent_level,
    LeadSignalORM.captured_at,
)


class HotLeadNotificationORM(Base):
    __tablename__ = "hot_lead_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    intent: Mapped[LeadIntent] = mapped_column(
        SAEnum(LeadIntent, name="hot_lead_notification_intent_enum", native_enum=True),
        nullable=False,
        default=LeadIntent.unknown,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_summary: Mapped[str] = mapped_column(String(255), nullable=False, default="N/A")
    market: Mapped[str] = mapped_column(String(255), nullable=False, default="N/A")
    timeline: Mapped[str] = mapped_column(String(100), nullable=False, default="exploring")
    destination: Mapped[str] = mapped_column(String(100), nullable=False, default="google_sheets")
    lead_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


Index(
    "idx_hot_lead_notifications_unread_created_at",
    HotLeadNotificationORM.unread,
    HotLeadNotificationORM.created_at,
)


class ForeclosurePropertyORM(Base):
    __tablename__ = "foreclosure_properties"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    zip: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    property_type: Mapped[str] = mapped_column(String(40), nullable=False, default="single_family")
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    estimated_value_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    auction_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    auction_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    minimum_bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


Index(
    "idx_foreclosure_properties_state_city_status_active",
    ForeclosurePropertyORM.state,
    ForeclosurePropertyORM.city,
    ForeclosurePropertyORM.status,
    ForeclosurePropertyORM.is_active,
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LeadProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    intent: LeadIntent = Field(default=LeadIntent.unknown)
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    target_market: Optional[str] = None
    # US cities/neighborhoods, e.g., "Brickell", "Williamsburg", "Downtown Austin"
    preferred_locations: List[str] = Field(default_factory=list)
    timeline: LeadTimeline = Field(default=LeadTimeline.exploring)
    property_type: PropertyType
    financing_type: FinancingType = Field(default=FinancingType.unknown)
    is_first_time_buyer: Optional[bool] = None
    consent_given: bool = Field(default=False)
    consent_timestamp: Optional[datetime] = None
    source: str
    created_at: datetime
    updated_at: datetime


class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    classification: LeadIntent
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: List[str]
    timestamp: datetime


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    heat_score: int = Field(ge=0, le=100)
    bucket: ScoreBucket
    signals: List[str]
    timestamp: datetime


class ComplianceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_id: uuid.UUID
    consent_verified: bool
    pii_redacted: bool
    blocked_claims: List[str]
    sanitized_transcript: str
    compliant: bool
    timestamp: datetime


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    area: str
    median_sale_price_usd: float
    price_per_sqft_usd: float
    median_rent_usd: float
    days_on_market: int
    snapshot_date: date
    source: str
    created_at: datetime


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class LeadSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source: SignalSource
    source_id: str
    username: Optional[str] = None
    content: str
    locations_mentioned: List[str] = Field(default_factory=list)
    apparent_intent: LeadIntent = Field(default=LeadIntent.unknown)
    intent_score: int = Field(ge=1, le=10)
    intent_level: SignalIntentLevel
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime
    converted_to_lead: bool = Field(default=False)
    lead_id: Optional[uuid.UUID] = None


class HotLeadNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    lead_id: uuid.UUID
    lead_name: Optional[str] = None
    intent: LeadIntent
    score: int = Field(ge=0, le=100)
    budget_summary: str
    market: str
    timeline: str
    destination: str
    lead_url: Optional[str] = None
    unread: bool = True
    created_at: datetime


class ForeclosureProperty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    property_type: str
    status: str
    estimated_value_usd: Optional[float] = None
    auction_date: Optional[datetime] = None
    auction_location: Optional[str] = None
    minimum_bid: Optional[float] = None
    source: str
    source_url: str
    description: str
    captured_at: datetime
    is_active: bool = True


__all__ = [
    # Enums
    "LeadIntent",
    "LeadTimeline",
    "PropertyType",
    "FinancingType",
    "ScoreBucket",
    "ChatRole",
    "SignalSource",
    "SignalIntentLevel",
    # ORM models
    "LeadProfileORM",
    "IntentResultORM",
    "ScoreResultORM",
    "ComplianceResultORM",
    "MarketSnapshotORM",
    "ChatMessageORM",
    "ConversationTranscriptORM",
    "LeadSignalORM",
    "HotLeadNotificationORM",
    "ForeclosurePropertyORM",
    # Pydantic schemas
    "LeadProfile",
    "IntentResult",
    "ScoreResult",
    "ComplianceResult",
    "MarketSnapshot",
    "ChatMessage",
    "LeadSignal",
    "HotLeadNotification",
    "ForeclosureProperty",
]

