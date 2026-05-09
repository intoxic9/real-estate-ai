"""
Notification service for routed hot leads.

Supports:
- generic webhook POST
- optional Slack webhook
- optional SendGrid email
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.schemas import HotLeadNotificationORM, LeadIntent


class NotificationService:
    def __init__(self) -> None:
        self.webhook_url = os.getenv("NOTIFICATION_WEBHOOK_URL", "").strip()
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY", "").strip()
        self.notification_email = os.getenv("NOTIFICATION_EMAIL", "").strip()
        self.frontend_base_url = (
            os.getenv("FRONTEND_BASE_URL")
            or os.getenv("FRONTEND_ORIGIN")
            or "http://localhost:3001"
        ).rstrip("/")

    async def notify_hot_lead_routed(
        self,
        db: AsyncSession,
        *,
        lead_id: UUID,
        lead_name: Optional[str],
        intent: LeadIntent,
        score: int,
        budget_summary: str,
        market: str,
        timeline: str,
        destination: str,
    ) -> None:
        lead_url = f"{self.frontend_base_url}/dashboard?leadId={lead_id}"
        notification = HotLeadNotificationORM(
            lead_id=lead_id,
            lead_name=lead_name,
            intent=intent,
            score=score,
            budget_summary=budget_summary,
            market=market,
            timeline=timeline,
            destination=destination,
            lead_url=lead_url,
            unread=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(notification)
        await db.commit()

        payload: dict[str, Any] = {
            "event": "hot_lead_routed",
            "lead_id": str(lead_id),
            "lead_name": lead_name,
            "score": score,
            "intent": intent.value,
            "budget": budget_summary,
            "market": market,
            "timeline": timeline,
            "destination": destination,
            "lead_url": lead_url,
            "created_at": notification.created_at.isoformat(),
        }

        if self.webhook_url:
            await self._post_json(self.webhook_url, payload)
        if self.slack_webhook_url:
            await self._send_slack(payload)
        if self.sendgrid_api_key and self.notification_email:
            await self._send_email(payload)

    async def _post_json(self, url: str, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(url, json=payload)
        except Exception:
            return

    async def _send_slack(self, payload: dict[str, Any]) -> None:
        text = (
            f"🔥 New Hot Lead! Score: {payload['score']} | Intent: {payload['intent']} | "
            f"Budget: {payload['budget']} | Market: {payload['market']} | Timeline: {payload['timeline']}\n"
            f"Lead: {payload['lead_url']}"
        )
        await self._post_json(self.slack_webhook_url, {"text": text})

    async def _send_email(self, payload: dict[str, Any]) -> None:
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;line-height:1.5;color:#0f172a">
          <h2 style="margin:0 0 12px 0;color:#1B2A4A">🔥 New Hot Lead Routed</h2>
          <p style="margin:0 0 8px 0"><strong>Score:</strong> {payload['score']}</p>
          <p style="margin:0 0 8px 0"><strong>Intent:</strong> {payload['intent']}</p>
          <p style="margin:0 0 8px 0"><strong>Budget:</strong> {payload['budget']}</p>
          <p style="margin:0 0 8px 0"><strong>Market:</strong> {payload['market']}</p>
          <p style="margin:0 0 8px 0"><strong>Timeline:</strong> {payload['timeline']}</p>
          <p style="margin:0 0 12px 0"><strong>Destination:</strong> {payload['destination']}</p>
          <p style="margin:0">
            <a href="{payload['lead_url']}" style="color:#2E75B6;text-decoration:none">
              Open lead in dashboard
            </a>
          </p>
        </div>
        """
        body = {
            "personalizations": [{"to": [{"email": self.notification_email}]}],
            "from": {"email": self.notification_email},
            "subject": "New Hot Lead Routed",
            "content": [{"type": "text/html", "value": html}],
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except Exception:
            return

