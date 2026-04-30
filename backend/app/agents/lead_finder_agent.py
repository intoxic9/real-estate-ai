"""
Lead Finder Agent.

Collects public intent signals from Reddit, Twitter/X, and Google Alerts.
"""

from __future__ import annotations

import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from langchain_groq import ChatGroq
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import GROQ_API_KEY_SEARCH
from ..core.schemas import LeadIntent, LeadSignalORM, SignalIntentLevel, SignalSource

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - optional at runtime if dependency missing
    DDGS = None  # type: ignore[assignment]

try:
    import praw
except Exception:  # pragma: no cover - optional at runtime if dependency missing
    praw = None

try:
    import feedparser
except Exception:  # pragma: no cover - optional at runtime if dependency missing
    feedparser = None

INTENT_KEYWORDS = [
    "relocating to",
    "moving to",
    "looking to buy",
    "first home",
    "house hunting",
    "apartment hunting",
    "selling my house",
    "real estate agent",
    "pre-approved",
    "mortgage",
]

DEFAULT_SUBREDDITS = [
    "RealEstate",
    "FirstTimeHomeBuyer",
    "moving",
    "personalfinance",
    "expats",
    "newjersey",
]

LOCATION_PATTERN = re.compile(
    r"\b(?:in|to|near|around)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}(?:,\s*[A-Z]{2})?)"
)
TWITTER_HANDLE_PATTERN = re.compile(r"twitter\.com/([A-Za-z0-9_]+)/status/", re.IGNORECASE)
SNIPPET_DATE_PREFIX_PATTERN = re.compile(r"^([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\s+[.·-]\s+(.*)$")

logger = logging.getLogger(__name__)


def search_social_signals(query: str, max_results: int = 10):
    try:
        if DDGS is None:
            return []
        results = list(DDGS().text(query, max_results=max_results))
        return results
    except Exception as e:  # noqa: BLE001
        print(f"Search error: {e}")
        return []


class SignalClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_level: SignalIntentLevel
    rationale: str


class IntentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str
    confidence: float = Field(ge=0.0, le=1.0)


class LeadFinderAgent:
    def __init__(self) -> None:
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "LeadIntelBot/1.0").strip()
        self.twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
        self.groq_api_key = (GROQ_API_KEY_SEARCH or os.getenv("GROQ_API_KEY", "")).strip()
        self.model_name = os.getenv("LEAD_FINDER_MODEL", "llama-3.1-8b-instant")
        self.target_subreddits = [
            s.strip() for s in os.getenv("LEAD_FINDER_SUBREDDITS", ",".join(DEFAULT_SUBREDDITS)).split(",") if s.strip()
        ]
        self.reddit_rss_urls = [
            f"https://www.reddit.com/r/{sub}/new/.rss"
            for sub in self.target_subreddits
        ]

    @staticmethod
    def _extract_locations(text: str) -> List[str]:
        found = {m.group(1).strip() for m in LOCATION_PATTERN.finditer(text)}
        return sorted(found)

    @staticmethod
    def _infer_apparent_intent(text: str) -> LeadIntent:
        lower = text.lower()
        if any(token in lower for token in ("sell my house", "selling my", "list my home", "home worth", "i own")):
            return LeadIntent.seller
        if any(token in lower for token in ("apartment hunting", "lease", "renting", "looking to rent")):
            return LeadIntent.renter
        if any(token in lower for token in ("refinance", "lower my rate", "refi")):
            return LeadIntent.refinance
        if any(token in lower for token in ("invest", "rental income", "flip")):
            return LeadIntent.buyer_investment
        if any(token in lower for token in ("looking to buy", "first home", "house hunting", "pre-approved", "mortgage")):
            return LeadIntent.buyer_primary
        return LeadIntent.unknown

    async def _classify_apparent_intent(self, content: str) -> LeadIntent:
        if self.groq_api_key:
            llm = ChatGroq(
                api_key=self.groq_api_key,
                model=self.model_name,
                temperature=0.2,
            ).with_structured_output(IntentClassification)
            prompt = (
                "Classify the intent of this social media post about real estate.\n\n"
                "Categories:\n"
                "- buyer_primary: Person wants to buy a home to LIVE IN\n"
                "- buyer_investment: Person wants to buy property as an INVESTMENT\n"
                "  (rental income, appreciation, vacation rental, second home)\n"
                "- seller: Person wants to SELL property they already own\n"
                "- renter: Person is looking to RENT a place to live\n"
                "- refinance: Person wants to refinance existing mortgage\n"
                "- not_relevant: Post is not about a real estate transaction\n\n"
                "Key signals:\n"
                "- 'buying property' / 'considering buying' / 'save for down payment' = BUYER\n"
                "- 'rental income' / 'renting it out' / 'investment' / 'appreciation' = buyer_investment\n"
                "- 'selling my house' / 'listing my property' / 'what is my home worth' = seller\n"
                "- 'looking for an apartment' / 'need a place to rent' = renter\n\n"
                "IMPORTANT: Someone who wants to BUY property and RENT IT OUT is a\n"
                "buyer_investment, NOT a seller. They are buying, not selling.\n\n"
                'Return ONLY valid JSON: {"intent": "...", "confidence": 0.0-1.0}\n\n'
                f"Post:\n{content}"
            )
            try:
                result = await llm.ainvoke(prompt)
                intent_raw = (result.intent or "").strip().lower()
                intent_map: dict[str, LeadIntent] = {
                    "buyer_primary": LeadIntent.buyer_primary,
                    "buyer_investment": LeadIntent.buyer_investment,
                    "seller": LeadIntent.seller,
                    "renter": LeadIntent.renter,
                    "refinance": LeadIntent.refinance,
                    "not_relevant": LeadIntent.unknown,
                }
                mapped = intent_map.get(intent_raw)
                if mapped is not None:
                    return mapped
            except Exception:
                pass

        return self._infer_apparent_intent(content)

    @staticmethod
    def _score_signal(text: str) -> int:
        lower = text.lower()
        score = 1
        if any(k in lower for k in INTENT_KEYWORDS):
            score += 3
        if any(k in lower for k in ("this week", "this weekend", "next month", "within 30 days", "asap")):
            score += 2
        if any(k in lower for k in ("pre-approved", "budget", "mortgage", "cash offer")):
            score += 2
        if LOCATION_PATTERN.search(text):
            score += 1
        if len(lower) > 180:
            score += 1
        return max(1, min(score, 10))

    async def _classify_intent_level(self, content: str, score: int) -> SignalIntentLevel:
        if self.groq_api_key:
            llm = ChatGroq(
                api_key=self.groq_api_key,
                model=self.model_name,
                temperature=0.2,
            ).with_structured_output(SignalClassification)
            prompt = (
                "Classify real-estate public signal intent level.\n"
                "Levels: strong_intent, moderate_intent, weak_intent, not_relevant.\n"
                f"Signal score: {score}\n"
                f"Content: {content}"
            )
            try:
                result = await llm.ainvoke(prompt)
                return result.intent_level
            except Exception:
                pass

        # Deterministic fallback.
        lower = content.lower()
        if score >= 8 and any(k in lower for k in ("pre-approved", "this weekend", "house hunting", "selling my house")):
            return SignalIntentLevel.strong_intent
        if score >= 5:
            return SignalIntentLevel.moderate_intent
        if score >= 3:
            return SignalIntentLevel.weak_intent
        return SignalIntentLevel.not_relevant

    async def _persist_signal(
        self,
        db: AsyncSession,
        *,
        source: SignalSource,
        source_id: str,
        username: Optional[str],
        content: str,
        captured_at: datetime,
        raw_data: Dict[str, Any],
    ) -> LeadSignalORM:
        existing = await db.execute(
            select(LeadSignalORM).where(
                LeadSignalORM.source == source,
                LeadSignalORM.source_id == source_id,
            )
        )
        existing_signal = existing.scalar_one_or_none()
        if existing_signal is not None:
            return existing_signal

        locations = self._extract_locations(content)
        apparent_intent = await self._classify_apparent_intent(content)
        score = self._score_signal(content)
        intent_level = await self._classify_intent_level(content, score)

        signal = LeadSignalORM(
            id=uuid.uuid4(),
            source=source,
            source_id=source_id,
            username=username,
            content=content,
            locations_mentioned=locations,
            apparent_intent=apparent_intent,
            intent_score=score,
            intent_level=intent_level,
            raw_data=raw_data,
            captured_at=captured_at,
            converted_to_lead=False,
            lead_id=None,
        )
        db.add(signal)
        return signal

    async def ingest_google_alert(
        self,
        db: AsyncSession,
        *,
        source_url: str,
        snippet: str,
        forwarded_by: Optional[str] = None,
        raw_email: Optional[str] = None,
    ) -> LeadSignalORM:
        content = f"{snippet}\nURL: {source_url}".strip()
        signal = await self._persist_signal(
            db,
            source=SignalSource.google_alerts,
            source_id=source_url,
            username=forwarded_by,
            content=content,
            captured_at=datetime.now(timezone.utc),
            raw_data={
                "source_url": source_url,
                "snippet": snippet,
                "forwarded_by": forwarded_by,
                "raw_email": raw_email,
            },
        )
        await db.commit()
        await db.refresh(signal)
        return signal

    async def ingest_reddit(self, db: AsyncSession, limit_per_keyword: int = 20) -> int:
        if praw and self.reddit_client_id and self.reddit_client_secret:
            logger.info("LeadFinder Reddit ingest using method=reddit_api")
            return await self._ingest_reddit_api(db, limit_per_keyword=limit_per_keyword)
        if feedparser is not None:
            logger.info("LeadFinder Reddit ingest using method=reddit_rss")
            inserted = await self._ingest_reddit_rss(db, limit_per_feed=limit_per_keyword)
            # Supplement RSS with DuckDuckGo search results.
            inserted += await self._ingest_reddit_ddgs(db, limit_per_query=min(10, limit_per_keyword))
            return inserted
        logger.info("LeadFinder Reddit ingest using method=ddgs_fallback")
        return await self._ingest_reddit_ddgs(db, limit_per_query=min(10, limit_per_keyword))

    async def _ingest_reddit_api(self, db: AsyncSession, limit_per_keyword: int = 20) -> int:
        if not (praw and self.reddit_client_id and self.reddit_client_secret):
            return 0

        client = praw.Reddit(
            client_id=self.reddit_client_id,
            client_secret=self.reddit_client_secret,
            user_agent=self.reddit_user_agent,
        )

        inserted = 0
        subreddit = client.subreddit("+".join(self.target_subreddits))
        for keyword in INTENT_KEYWORDS:
            for post in subreddit.search(keyword, sort="new", limit=limit_per_keyword):
                post_id = str(getattr(post, "id", ""))
                if not post_id:
                    continue
                created_ts = float(getattr(post, "created_utc", 0) or 0)
                created_at = datetime.fromtimestamp(created_ts or datetime.now(timezone.utc).timestamp(), tz=timezone.utc)
                content = f"{getattr(post, 'title', '')}\n{getattr(post, 'selftext', '')}".strip()
                raw = {
                    "subreddit": str(getattr(post, "subreddit", "")),
                    "permalink": getattr(post, "permalink", ""),
                    "score": getattr(post, "score", None),
                    "num_comments": getattr(post, "num_comments", None),
                }
                await self._persist_signal(
                    db,
                    source=SignalSource.reddit_api,
                    source_id=post_id,
                    username=str(getattr(post, "author", "")) or None,
                    content=content,
                    captured_at=created_at,
                    raw_data=raw,
                )
                inserted += 1
        await db.commit()
        return inserted

    async def _ingest_reddit_rss(self, db: AsyncSession, limit_per_feed: int = 20) -> int:
        if feedparser is None:
            return 0
        inserted = 0
        for url in self.reddit_rss_urls:
            parsed = feedparser.parse(url)
            for entry in list(parsed.entries or [])[:limit_per_feed]:
                source_id = str(getattr(entry, "id", "") or getattr(entry, "link", ""))
                if not source_id:
                    continue
                title = str(getattr(entry, "title", "") or "").strip()
                summary = str(getattr(entry, "summary", "") or "").strip()
                content = f"{title}\n{summary}".strip()
                if not content:
                    continue
                if not any(keyword in content.lower() for keyword in INTENT_KEYWORDS):
                    continue
                published = str(getattr(entry, "published", "") or "")
                captured_at = datetime.now(timezone.utc)
                if published:
                    try:
                        captured_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                raw = {
                    "link": str(getattr(entry, "link", "") or ""),
                    "subreddit_feed": url,
                }
                await self._persist_signal(
                    db,
                    source=SignalSource.reddit_rss,
                    source_id=source_id,
                    username=getattr(entry, "author", None),
                    content=content,
                    captured_at=captured_at,
                    raw_data=raw,
                )
                inserted += 1
        await db.commit()
        return inserted

    async def _ingest_reddit_ddgs(self, db: AsyncSession, limit_per_query: int = 10) -> int:
        if DDGS is None:
            return 0
        inserted = 0
        queries = [
            "site:reddit.com relocating to Austin",
            "site:reddit.com first time home buyer New Jersey",
            "site:reddit.com selling my house",
            "site:reddit.com pre-approved mortgage",
        ]
        for query in queries:
            results = search_social_signals(query, max_results=min(limit_per_query, 10))
            for item in results or []:
                href = str(item.get("href") or item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                body = str(item.get("body") or item.get("snippet") or "").strip()
                if not href:
                    continue
                content = f"{title}\n{body}".strip() or href

                captured_at = datetime.now(timezone.utc)
                date_hint = SNIPPET_DATE_PREFIX_PATTERN.match(body.strip()) or SNIPPET_DATE_PREFIX_PATTERN.match(title.strip())
                if date_hint:
                    # Example: "Apr 29, 2026 - ...": parse first capture group
                    try:
                        captured_at = datetime.strptime(date_hint.group(1), "%b %d, %Y").replace(tzinfo=timezone.utc)
                    except Exception:
                        captured_at = datetime.now(timezone.utc)

                # URL patterns for reddit posts: /r/<subreddit>/comments/<id>/...
                subreddit_match = re.search(r"reddit\\.com/r/([^/]+)/", href)
                apparent_subreddit = subreddit_match.group(1) if subreddit_match else None
                await self._persist_signal(
                    db,
                    source=SignalSource.reddit_rss,
                    source_id=href,
                    username=None,
                    content=content,
                    captured_at=captured_at,
                    raw_data={
                        "url": href,
                        "query": query,
                        "apparent_subreddit": apparent_subreddit,
                        "source": "ddgs",
                        "title": title,
                    },
                )
                inserted += 1
        await db.commit()
        return inserted

    async def ingest_twitter(self, db: AsyncSession, max_results: int = 25) -> int:
        if self.twitter_bearer_token:
            logger.info("LeadFinder Twitter ingest using method=twitter_api")
            return await self._ingest_twitter_api(db, max_results=max_results)
        logger.info("LeadFinder Twitter ingest using method=twitter_google")
        return await self._ingest_twitter_google(db, limit_per_query=min(max_results, 10))

    async def _ingest_twitter_api(self, db: AsyncSession, max_results: int = 25) -> int:
        if not self.twitter_bearer_token:
            return 0
        inserted = 0
        headers = {"Authorization": f"Bearer {self.twitter_bearer_token}"}
        query = " OR ".join(f"\"{k}\"" for k in INTENT_KEYWORDS) + " -is:retweet lang:en"
        params = {
            "query": query,
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": "created_at,author_id,geo",
            "user.fields": "username,location",
            "expansions": "author_id",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        includes = payload.get("includes", {})
        users = {u.get("id"): u for u in includes.get("users", [])}
        tweets = payload.get("data", []) or []
        for tweet in tweets:
            source_id = str(tweet.get("id", ""))
            if not source_id:
                continue
            existing = await db.execute(
                select(LeadSignalORM.id).where(
                    LeadSignalORM.source == SignalSource.twitter,
                    LeadSignalORM.source_id == source_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            user = users.get(tweet.get("author_id"), {})
            created_at_str = tweet.get("created_at")
            created_at = (
                datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if isinstance(created_at_str, str)
                else datetime.now(timezone.utc)
            )
            text = str(tweet.get("text", "")).strip()
            location = user.get("location")
            content = f"{text}\nLocation: {location}" if location else text
            await self._persist_signal(
                db,
                source=SignalSource.twitter,
                source_id=source_id,
                username=user.get("username"),
                content=content,
                captured_at=created_at,
                raw_data=tweet,
            )
            inserted += 1
        await db.commit()
        return inserted

    @staticmethod
    def _extract_twitter_handle_from_url(url: str) -> Optional[str]:
        match = TWITTER_HANDLE_PATTERN.search(url)
        return match.group(1) if match else None

    async def _ingest_twitter_google(self, db: AsyncSession, limit_per_query: int = 10) -> int:
        if DDGS is None:
            return 0
        inserted = 0
        queries = [
            "site:twitter.com house hunting Denver",
        ]
        for query in queries:
            results = search_social_signals(query, max_results=min(limit_per_query, 10))
            for item in results or []:
                link = str(item.get("href") or item.get("url") or "").strip()
                if not link or "twitter.com/" not in link:
                    continue
                title = str(item.get("title") or "").strip()
                snippet = str(item.get("body") or item.get("snippet") or "").strip()
                handle = self._extract_twitter_handle_from_url(link)

                captured_at = datetime.now(timezone.utc)
                m = SNIPPET_DATE_PREFIX_PATTERN.match(snippet.strip()) or SNIPPET_DATE_PREFIX_PATTERN.match(title.strip())
                date_hint = m.group(1).strip() if m else None
                if date_hint:
                    try:
                        captured_at = datetime.strptime(date_hint, "%b %d, %Y").replace(tzinfo=timezone.utc)
                    except Exception:
                        captured_at = datetime.now(timezone.utc)

                content = snippet or title
                if not content:
                    continue
                if not any(keyword in content.lower() for keyword in INTENT_KEYWORDS):
                    continue
                if handle:
                    content = f"@{handle}: {content}"

                await self._persist_signal(
                    db,
                    source=SignalSource.twitter_google,
                    source_id=link,
                    username=handle,
                    content=content,
                    captured_at=captured_at,
                    raw_data={
                        "query": query,
                        "title": title,
                        "snippet": snippet,
                        "link": link,
                        "date_hint": date_hint,
                        "source": "ddgs",
                    },
                )
                inserted += 1
        await db.commit()
        return inserted
