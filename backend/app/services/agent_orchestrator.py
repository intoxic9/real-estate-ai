"""
Agent orchestrator that runs the multi-agent pipeline.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, update

from ..agents.compliance_agent import ComplianceAgent
from ..agents.conversation_agent import ConversationAgent
from ..agents.intent_agent import IntentAgent
from ..agents.routing_agent import RoutingAgent
from ..agents.scoring_agent import ScoringAgent
from ..core.schemas import ChatRole, ConversationTranscriptORM, LeadIntent, LeadProfile, PropertyType


logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self) -> None:
        self.conversation_agent = ConversationAgent()
        self.compliance_agent = ComplianceAgent()
        self.intent_agent = IntentAgent()
        self.scoring_agent = ScoringAgent()
        self.routing_agent = RoutingAgent()

        # In-memory session state/transcript store (replace with Redis/DB for production scale-out).
        self._session_state: Dict[str, Dict[str, Any]] = {}
        self._session_transcript: Dict[str, List[Dict[str, Any]]] = {}
        self._partial_results: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _filter_valid_lead_fields(lead_data: Dict[str, Any]) -> Dict[str, Any]:
        valid_fields = set(LeadProfile.model_fields.keys())
        return {k: v for k, v in lead_data.items() if k in valid_fields}

    @staticmethod
    def _sanitize_lead_data_values(lead_data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(lead_data)
        for key in ("budget_min", "budget_max", "is_first_time_buyer", "full_name", "email", "phone", "target_market"):
            if isinstance(cleaned.get(key), str) and cleaned[key].strip() == "":
                cleaned[key] = None
        if isinstance(cleaned.get("preferred_locations"), list):
            cleaned["preferred_locations"] = [
                loc for loc in cleaned["preferred_locations"] if not (isinstance(loc, str) and loc.strip() == "")
            ]
        return cleaned

    def _get_state(self, session_id: str) -> Dict[str, Any]:
        return dict(self._session_state.get(session_id) or {})

    def _set_state(self, session_id: str, state: Dict[str, Any]) -> None:
        self._session_state[session_id] = dict(state)

    async def _append_transcript(
        self,
        session_id: str,
        role: str,
        content: str,
        db: Optional[AsyncSession] = None,
    ) -> None:
        timestamp = datetime.now(timezone.utc)
        entry = {
            "role": role,
            "content": content,
            "timestamp": timestamp.isoformat(),
        }
        self._session_transcript.setdefault(session_id, []).append(entry)

        if db is None:
            return

        try:
            chat_role = ChatRole(role)
        except Exception:
            return

        # Attach lead_id when known so /api/leads/{id} can reliably load transcript.
        lead_id: Optional[UUID] = None
        profile = self.get_profile(session_id)
        if profile is not None:
            try:
                lead_id = UUID(str(profile.id))
            except Exception:
                lead_id = None

        db.add(
            ConversationTranscriptORM(
                session_id=session_id,
                lead_id=lead_id,
                role=chat_role,
                content=content,
                timestamp=timestamp,
            )
        )
        await db.commit()

    async def get_transcript(
        self,
        session_id: str,
        db: Optional[AsyncSession] = None,
    ) -> List[Dict[str, Any]]:
        in_memory = list(self._session_transcript.get(session_id) or [])
        if in_memory:
            return in_memory

        if db is None:
            return []

        rows = (
            await db.execute(
                select(ConversationTranscriptORM)
                .where(ConversationTranscriptORM.session_id == session_id)
                .order_by(ConversationTranscriptORM.timestamp.asc(), ConversationTranscriptORM.id.asc())
            )
        ).scalars().all()
        if not rows:
            return []

        restored = [
            {
                "role": row.role.value if isinstance(row.role, ChatRole) else str(row.role),
                "content": row.content,
                "timestamp": row.timestamp.isoformat(),
            }
            for row in rows
        ]
        self._session_transcript[session_id] = restored
        return list(restored)

    def _is_user_end_chat(self, message: str) -> bool:
        text = message.strip().lower()
        return text in {"end", "done", "that's all", "thats all", "stop", "end chat", "bye"}

    @staticmethod
    def _has_uncertain_buy_message(message: str) -> bool:
        text = message.lower()
        has_buy_signal = any(
            phrase in text for phrase in ("buy", "purchase", "first home", "first-time buyer", "first time buyer")
        )
        has_uncertainty = any(
            phrase in text for phrase in ("not sure", "not really sure", "just browsing", "just curious", "maybe someday", "just looking")
        )
        return has_buy_signal and has_uncertainty

    def get_profile(self, session_id: str) -> Optional[LeadProfile]:
        state = self._get_state(session_id)
        lead_data = dict(state.get("lead_profile") or {})
        if not lead_data:
            return None

        now = datetime.now(timezone.utc)
        # Normalize required fields for LeadProfile model construction.
        lead_data.setdefault("source", "chatbot")
        lead_data.setdefault("created_at", now)
        lead_data["updated_at"] = now

        # If still missing property_type, fallback to a neutral default until complete.
        lead_data.setdefault("property_type", PropertyType.apartment)
        filtered_data = self._filter_valid_lead_fields(lead_data)
        filtered_data = self._sanitize_lead_data_values(filtered_data)
        return LeadProfile(**filtered_data)

    async def process_message(
        self,
        session_id: str,
        message: str,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        timings_ms: Dict[str, float] = {}
        partial: Dict[str, Any] = self._partial_results.get(session_id, {})
        pipeline_already_ran = bool(partial.get("pipeline_ran"))

        await self._append_transcript(session_id, "user", message, db=db)

        # 1. Conversation agent
        conv_t0 = perf_counter()
        conv_result, new_state = await self.conversation_agent.handle_turn(
            user_message=message,
            state=self._get_state(session_id),
            session_id=session_id,
            db=db,
        )
        if self._has_uncertain_buy_message(message):
            conv_result.lead_profile_updates["intent"] = LeadIntent.unknown.value
            state_profile = dict(new_state.get("lead_profile") or {})
            state_profile["intent"] = LeadIntent.unknown.value
            new_state["lead_profile"] = state_profile
        timings_ms["conversation_agent"] = round((perf_counter() - conv_t0) * 1000, 2)
        self._set_state(session_id, new_state)
        await self._append_transcript(session_id, "assistant", conv_result.response, db=db)

        state_profile = dict(new_state.get("lead_profile") or {})
        consent_from_profile = bool(state_profile.get("consent_given"))
        should_run_pipeline = (
            conv_result.is_complete
            or self._is_user_end_chat(message)
            or (consent_from_profile and not pipeline_already_ran)
        )
        if not should_run_pipeline:
            return {
                "response": conv_result.response,
                "pipeline_complete": False,
                "lead_profile_updates": conv_result.lead_profile_updates,
                "widget": conv_result.widget,
                "timings_ms": timings_ms,
            }

        profile = self.get_profile(session_id)
        transcript = await self.get_transcript(session_id, db=db)
        truncated_transcript = transcript[-10:] if len(transcript) > 10 else transcript
        if profile is None:
            return {
                "response": conv_result.response,
                "pipeline_complete": False,
                "lead_profile_updates": conv_result.lead_profile_updates,
                "widget": conv_result.widget,
                "timings_ms": timings_ms,
                "error": "Profile could not be constructed from session state.",
            }

        # Backfill conversation_transcripts for older sessions (created before we persisted
        # transcripts to DB). We only backfill if the table has zero rows for this session.
        existing_cnt = (
            await db.execute(
                select(func.count(ConversationTranscriptORM.id)).where(
                    ConversationTranscriptORM.session_id == session_id
                )
            )
        ).scalar_one()

        if existing_cnt == 0 and transcript:
            def _redact_pii(text: str) -> str:
                import re

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

            from datetime import datetime as _dt

            for item in transcript:
                role_raw = str(item.get("role") or "")
                try:
                    role = ChatRole(role_raw)
                except Exception:
                    continue
                if role not in {ChatRole.user, ChatRole.assistant}:
                    continue
                content = str(item.get("content") or "")
                ts_raw = item.get("timestamp")
                try:
                    ts = _dt.fromisoformat(ts_raw) if ts_raw else datetime.now(timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)

                db.add(
                    ConversationTranscriptORM(
                        session_id=session_id,
                        lead_id=None,
                        role=role,
                        content=_redact_pii(content),
                        timestamp=ts,
                    )
                )

            await db.commit()

        # 2a-d. Full pipeline with error isolation + partial result retention.
        compliance = None
        intent = None
        score = None
        routing = None

        try:
            t0 = perf_counter()
            compliance = await self.compliance_agent.evaluate(profile, truncated_transcript)
            timings_ms["compliance_agent"] = round((perf_counter() - t0) * 1000, 2)
            partial["compliance"] = compliance.model_dump()
        except Exception as exc:
            logger.exception("Compliance agent failed for session %s: %s", session_id, exc)
            partial["compliance_error"] = str(exc)

        try:
            t0 = perf_counter()
            intent = await self.intent_agent.classify(profile, truncated_transcript)
            timings_ms["intent_agent"] = round((perf_counter() - t0) * 1000, 2)
            partial["intent"] = intent.model_dump()
        except Exception as exc:
            logger.exception("Intent agent failed for session %s: %s", session_id, exc)
            partial["intent_error"] = str(exc)

        try:
            if intent is not None:
                t0 = perf_counter()
                score = await self.scoring_agent.score(profile, intent, truncated_transcript)
                timings_ms["scoring_agent"] = round((perf_counter() - t0) * 1000, 2)
                partial["score"] = score.model_dump()
        except Exception as exc:
            logger.exception("Scoring agent failed for session %s: %s", session_id, exc)
            partial["score_error"] = str(exc)

        try:
            if compliance is not None and intent is not None and score is not None:
                t0 = perf_counter()
                routing = await self.routing_agent.route(
                    db=db,
                    lead_profile=profile,
                    intent_result=intent,
                    score_result=score,
                    compliance_result=compliance,
                )
                timings_ms["routing_agent"] = round((perf_counter() - t0) * 1000, 2)
                partial["routing"] = routing.model_dump()

                # Link persisted conversation turns to the newly created lead record.
                await db.execute(
                    update(ConversationTranscriptORM)
                    .where(ConversationTranscriptORM.session_id == session_id)
                    .where(ConversationTranscriptORM.lead_id.is_(None))
                    .values(lead_id=profile.id)
                )
                await db.commit()
        except Exception as exc:
            logger.exception("Routing agent failed for session %s: %s", session_id, exc)
            partial["routing_error"] = str(exc)

        partial["pipeline_ran"] = True
        self._partial_results[session_id] = partial

        return {
            "response": conv_result.response,
            "pipeline_complete": True,
            "widget": conv_result.widget,
            "lead_id": str(profile.id),
            "score": score.heat_score if score else None,
            "bucket": score.bucket.value if score else None,
            "routed": routing.routed if routing else False,
            "destination": routing.destination if routing else "partial",
            "reason": routing.reason if routing else "Pipeline partially failed; partial results stored.",
            "timings_ms": timings_ms,
            "errors": {k: v for k, v in partial.items() if k.endswith("_error")},
        }

