from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.schemas import LeadSignalORM, MarketSnapshotORM, SignalIntentLevel

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover
    DDGS = None  # type: ignore[assignment]


DealType = Literal["price_drop", "new_listing", "foreclosure", "below_market"]


@dataclass
class DealRecord:
    id: str
    description: str
    source: str
    location: str
    price_or_value: Optional[float]
    why_deal: str
    deal_type: DealType
    property_type: str
    context: str
    created_at: datetime


class DealFinderService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, list[DealRecord]]] = {}

    @staticmethod
    def _cache_key(city: str, deal_type: str) -> str:
        return f"{city.strip().lower()}::{deal_type}"

    @staticmethod
    def _query_for_type(city: str, deal_type: DealType) -> str:
        if deal_type == "price_drop":
            return f"site:reddit.com {city} price drop house"
        if deal_type == "new_listing":
            return f"site:reddit.com {city} new listing home"
        if deal_type == "foreclosure":
            return f"site:reddit.com {city} foreclosure auction"
        return f"site:reddit.com {city} below market home deal"

    @staticmethod
    def _why_for_type(deal_type: DealType, content: str) -> str:
        lower = content.lower()
        if deal_type == "price_drop":
            return "Price dropped recently." if "drop" in lower else "Potential markdown opportunity."
        if deal_type == "new_listing":
            return "Newly listed with early-mover opportunity."
        if deal_type == "foreclosure":
            return "Possible foreclosure or distressed sale signal."
        return "Appears below market relative to area signals."

    @staticmethod
    def _extract_price(text: str) -> Optional[float]:
        import re

        m = re.search(r"\$([0-9][0-9,]{3,})", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    async def _fetch_ddg(self, city: str, deal_type: DealType, limit: int = 8) -> list[DealRecord]:
        if DDGS is None:
            return []
        query = self._query_for_type(city, deal_type)

        def _run() -> list[dict[str, Any]]:
            try:
                return list(DDGS().text(query, max_results=limit))
            except Exception:
                return []

        rows = await asyncio.to_thread(_run)
        results: list[DealRecord] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            body = str(row.get("body") or row.get("snippet") or "").strip()
            href = str(row.get("href") or row.get("url") or "").strip()
            content = f"{title}. {body}".strip()
            if not content:
                continue
            results.append(
                DealRecord(
                    id=str(uuid.uuid4()),
                    description=content[:260],
                    source="Reddit",
                    location=city,
                    price_or_value=self._extract_price(content),
                    why_deal=self._why_for_type(deal_type, content),
                    deal_type=deal_type,
                    property_type="any",
                    context=f"{content}\nSource URL: {href}",
                    created_at=datetime.now(timezone.utc),
                )
            )
        return results

    async def _fetch_hud(self, city: str) -> list[DealRecord]:
        if DDGS is None:
            return []

        def _run() -> list[dict[str, Any]]:
            try:
                q = f"site:hudhomestore.gov {city} homes"
                return list(DDGS().text(q, max_results=5))
            except Exception:
                return []

        rows = await asyncio.to_thread(_run)
        deals: list[DealRecord] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            body = str(row.get("body") or row.get("snippet") or "").strip()
            href = str(row.get("href") or row.get("url") or "").strip()
            content = f"{title}. {body}".strip()
            if not content:
                continue
            deals.append(
                DealRecord(
                    id=str(uuid.uuid4()),
                    description=content[:260],
                    source="HUD",
                    location=city,
                    price_or_value=self._extract_price(content),
                    why_deal="HUD/public listing opportunity.",
                    deal_type="foreclosure",
                    property_type="any",
                    context=f"{content}\nSource URL: {href}",
                    created_at=datetime.now(timezone.utc),
                )
            )
        return deals

    async def _fetch_signals(self, db: AsyncSession, city: str, deal_type: DealType) -> list[DealRecord]:
        q = (
            select(LeadSignalORM)
            .where(LeadSignalORM.content.ilike(f"%{city}%"))
            .where(
                or_(
                    LeadSignalORM.intent_level == SignalIntentLevel.strong_intent,
                    LeadSignalORM.intent_level == SignalIntentLevel.moderate_intent,
                )
            )
            .order_by(LeadSignalORM.captured_at.desc())
            .limit(10)
        )
        rows = (await db.execute(q)).scalars().all()
        return [
            DealRecord(
                id=str(row.id),
                description=row.content[:260],
                source=f"Signal:{row.source.value}",
                location=", ".join(row.locations_mentioned or [city]),
                price_or_value=self._extract_price(row.content),
                why_deal=self._why_for_type(deal_type, row.content),
                deal_type=deal_type,
                property_type="any",
                context=row.content,
                created_at=row.captured_at,
            )
            for row in rows
        ]

    async def search_deals(
        self,
        db: AsyncSession,
        *,
        city: str,
        deal_type: DealType = "below_market",
        property_type: Optional[str] = None,
        max_price: Optional[float] = None,
    ) -> list[DealRecord]:
        key = self._cache_key(city, deal_type)
        now = datetime.now(timezone.utc)
        cached = self._cache.get(key)
        if cached and (now - cached[0]).total_seconds() < 24 * 3600:
            deals = cached[1]
        else:
            ddg, sig, hud = await asyncio.gather(
                self._fetch_ddg(city, deal_type),
                self._fetch_signals(db, city, deal_type),
                self._fetch_hud(city),
            )
            deals = sorted([*ddg, *sig, *hud], key=lambda d: d.created_at, reverse=True)[:30]
            self._cache[key] = (now, deals)

        if property_type and property_type != "any":
            deals = [d for d in deals if property_type.lower() in d.description.lower()]
        if max_price is not None:
            deals = [d for d in deals if d.price_or_value is None or d.price_or_value <= max_price]
        return deals

    async def refresh_default_cities(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        city_csv = os.getenv("DEALS_DEFAULT_CITIES", "Austin,Miami,New York Metro")
        cities = [c.strip() for c in city_csv.split(",") if c.strip()]
        async with session_factory() as db:
            for city in cities:
                for deal_type in ("price_drop", "new_listing", "foreclosure", "below_market"):
                    await self.search_deals(db, city=city, deal_type=deal_type)  # warm cache

    async def run_daily_refresh_loop(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        while True:
            try:
                await self.refresh_default_cities(session_factory)
            except Exception:
                pass
            await asyncio.sleep(24 * 3600)

