from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.schemas import ForeclosurePropertyORM

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover
    DDGS = None  # type: ignore[assignment]

try:
    import feedparser
except Exception:  # pragma: no cover
    feedparser = None  # type: ignore[assignment]


STATUS_VALUES = {"pre_foreclosure", "auction_scheduled", "bank_owned_reo", "hud_home"}
TYPE_VALUES = {"single_family", "condo", "multi_family", "land"}
SOURCE_VALUES = {"hud", "fannie_mae", "county_records", "public_listing"}


class ForeclosureService:
    def __init__(self) -> None:
        self.default_states = [
            s.strip() for s in os.getenv("FORECLOSURE_DEFAULT_STATES", "NJ,TX,FL,CA").split(",") if s.strip()
        ]
        self.rss_feeds = [
            f.strip() for f in os.getenv("FORECLOSURE_RSS_FEEDS", "").split(",") if f.strip()
        ]

    @staticmethod
    def _guess_status(text: str, source: str) -> str:
        lower = text.lower()
        if source == "hud":
            return "hud_home"
        if "fannie" in lower or "homepath" in lower or source == "fannie_mae":
            return "bank_owned_reo"
        if "auction" in lower:
            return "auction_scheduled"
        if "pre-foreclosure" in lower or "pre foreclosure" in lower:
            return "pre_foreclosure"
        return "bank_owned_reo"

    @staticmethod
    def _guess_property_type(text: str) -> str:
        lower = text.lower()
        if "condo" in lower:
            return "condo"
        if "multi" in lower or "duplex" in lower or "triplex" in lower:
            return "multi_family"
        if "land" in lower or "lot" in lower:
            return "land"
        return "single_family"

    @staticmethod
    def _extract_price(text: str) -> Optional[float]:
        m = re.search(r"\$([0-9][0-9,]{3,})", text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_zip(text: str) -> Optional[str]:
        m = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
        return m.group(1) if m else None

    @staticmethod
    def _extract_auction_date(text: str) -> Optional[datetime]:
        patterns = [r"(\b[A-Za-z]{3,9}\s+\d{1,2},\s+20\d{2}\b)", r"(\b20\d{2}-\d{2}-\d{2}\b)"]
        for pat in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            raw = m.group(1).strip()
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        return None

    async def _search_ddg(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if DDGS is None:
            return []

        def _run() -> list[dict[str, Any]]:
            try:
                return list(DDGS().text(query, max_results=limit))
            except Exception:
                return []

        return await asyncio.to_thread(_run)

    async def _persist(
        self,
        db: AsyncSession,
        *,
        address: str,
        city: Optional[str],
        state: Optional[str],
        zip_code: Optional[str],
        property_type: str,
        status: str,
        estimated_value_usd: Optional[float],
        auction_date: Optional[datetime],
        auction_location: Optional[str],
        minimum_bid: Optional[float],
        source: str,
        source_url: str,
        description: str,
    ) -> None:
        existing = (
            await db.execute(
                select(ForeclosurePropertyORM).where(
                    and_(
                        ForeclosurePropertyORM.address == address,
                        ForeclosurePropertyORM.source == source,
                        ForeclosurePropertyORM.source_url == source_url,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.city = city
            existing.state = state
            existing.zip = zip_code
            existing.property_type = property_type
            existing.status = status
            existing.estimated_value_usd = estimated_value_usd
            existing.auction_date = auction_date
            existing.auction_location = auction_location
            existing.minimum_bid = minimum_bid
            existing.description = description
            existing.captured_at = datetime.now(timezone.utc)
            existing.is_active = True
            return

        db.add(
            ForeclosurePropertyORM(
                id=uuid.uuid4(),
                address=address,
                city=city,
                state=state,
                zip=zip_code,
                property_type=property_type if property_type in TYPE_VALUES else "single_family",
                status=status if status in STATUS_VALUES else "bank_owned_reo",
                estimated_value_usd=estimated_value_usd,
                auction_date=auction_date,
                auction_location=auction_location,
                minimum_bid=minimum_bid,
                source=source if source in SOURCE_VALUES else "public_listing",
                source_url=source_url,
                description=description,
                captured_at=datetime.now(timezone.utc),
                is_active=True,
            )
        )

    async def refresh(self, db: AsyncSession, *, state: str, city: Optional[str] = None, county: Optional[str] = None) -> int:
        location_query = f"{city}, {state}" if city else state
        queries = [
            (f"site:hudhomestore.gov {state}", "hud"),
            (f"site:homepath.fanniemae.com {state}", "fannie_mae"),
            (f"{county or state} foreclosure auction notice 2026", "county_records"),
        ]
        inserted = 0
        for query, source in queries:
            results = await self._search_ddg(query, limit=12)
            for row in results:
                title = str(row.get("title") or "").strip()
                body = str(row.get("body") or row.get("snippet") or "").strip()
                url = str(row.get("href") or row.get("url") or "").strip()
                if not url:
                    continue
                description = f"{title}. {body}".strip()
                address = title or description[:120] or f"Listing in {location_query}"
                status = self._guess_status(description, source)
                prop_type = self._guess_property_type(description)
                estimated = self._extract_price(description)
                min_bid = estimated * 0.8 if estimated else None
                auction_date = self._extract_auction_date(description)
                zip_code = self._extract_zip(description)
                await self._persist(
                    db,
                    address=address,
                    city=city,
                    state=state,
                    zip_code=zip_code,
                    property_type=prop_type,
                    status=status,
                    estimated_value_usd=estimated,
                    auction_date=auction_date,
                    auction_location=county or city or state,
                    minimum_bid=min_bid,
                    source=source,
                    source_url=url,
                    description=description,
                )
                inserted += 1

        if feedparser is not None and self.rss_feeds:
            for feed_url in self.rss_feeds:
                parsed = feedparser.parse(feed_url)
                for entry in list(parsed.entries or [])[:10]:
                    title = str(getattr(entry, "title", "") or "").strip()
                    summary = str(getattr(entry, "summary", "") or "").strip()
                    link = str(getattr(entry, "link", "") or "").strip()
                    if not link:
                        continue
                    description = f"{title}. {summary}".strip()
                    if state.lower() not in description.lower():
                        continue
                    await self._persist(
                        db,
                        address=title or f"Listing in {state}",
                        city=city,
                        state=state,
                        zip_code=self._extract_zip(description),
                        property_type=self._guess_property_type(description),
                        status=self._guess_status(description, "public_listing"),
                        estimated_value_usd=self._extract_price(description),
                        auction_date=self._extract_auction_date(description),
                        auction_location=county or city or state,
                        minimum_bid=None,
                        source="public_listing",
                        source_url=link,
                        description=description,
                    )
                    inserted += 1
        await db.commit()
        return inserted

    async def run_daily_refresh_loop(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        while True:
            try:
                async with session_factory() as db:
                    for state in self.default_states:
                        await self.refresh(db, state=state)
            except Exception:
                pass
            await asyncio.sleep(24 * 3600)

