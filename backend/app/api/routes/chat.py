"""
Chat-related API routes.

For now these handlers return mock data and are wired with proper
request/response validation and database session dependency so that
real logic can be added later.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import ChatMessage, LeadProfile
from ...services.agent_orchestrator import AgentOrchestrator


router = APIRouter(prefix="/api/chat", tags=["chat"])
orchestrator = AgentOrchestrator()


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str
    lead_profile: Optional[LeadProfile] = None
    recommended_products: List[Any] = Field(default_factory=list)
    pipeline_complete: bool = False
    lead_profile_updates: Optional[dict[str, Any]] = None
    lead_id: Optional[str] = None
    score: Optional[int] = None
    bucket: Optional[str] = None
    routed: bool = False
    destination: Optional[str] = None
    reason: Optional[str] = None
    timings_ms: Optional[dict[str, float]] = None
    errors: Optional[dict[str, Any]] = None


@router.post(
    "/message",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    payload: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatMessageResponse:
    """
    Accept a chat message and run the multi-agent orchestration pipeline.
    """
    result = await orchestrator.process_message(
        session_id=payload.session_id,
        message=payload.message,
        db=db,
    )

    profile = orchestrator.get_profile(payload.session_id)
    return ChatMessageResponse(
        response=result.get("response", ""),
        lead_profile=profile,
        recommended_products=[],
        pipeline_complete=bool(result.get("pipeline_complete", False)),
        lead_profile_updates=result.get("lead_profile_updates"),
        lead_id=result.get("lead_id"),
        score=result.get("score"),
        bucket=result.get("bucket"),
        routed=bool(result.get("routed", False)),
        destination=result.get("destination"),
        reason=result.get("reason"),
        timings_ms=result.get("timings_ms"),
        errors=result.get("errors"),
    )


@router.get(
    "/history/{session_id}",
    response_model=List[ChatMessage],
    status_code=status.HTTP_200_OK,
)
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[ChatMessage]:
    """
    Return mock chat history for the given session.
    """

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required",
        )

    _ = db
    items = orchestrator.get_transcript(session_id)
    return [
        ChatMessage(
            role=item.get("role", "system"),  # type: ignore[arg-type]
            content=item.get("content", ""),
            timestamp=datetime.fromisoformat(item.get("timestamp")) if item.get("timestamp") else datetime.now(timezone.utc),
            metadata=None,
        )
        for item in items
    ]


__all__ = ["router"]

