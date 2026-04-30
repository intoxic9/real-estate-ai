"""
US market data ingestion service.

Data sources (legal/public):
- Redfin Data Center CSV exports
- FRED API (mortgage, housing starts, CPI shelter)
- US Census / ACS API
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from zipfile import ZipFile

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.schemas import MarketSnapshotORM


REDFIN_DATA_CENTER_URL = "https://www.redfin.com/news/data-center/"
FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
CENSUS_ACS_BASE = "https://api.census.gov/data"


@dataclass
class ExtendedMarketSnapshot:
    """Normalized market snapshot with optional macro overlays."""

    area: str
    snapshot_date: date
    median_sale_price_usd: float
    price_per_sqft_usd: float
    median_rent_usd: float
    days_on_market: int
    source: str

    # Optional overlays (generated/fetched, not yet persisted in current schema).
    inventory_months: Optional[float] = None
    mortgage_rate_30y: Optional[float] = None
    housing_starts: Optional[float] = None
    cpi_shelter_index: Optional[float] = None
    median_household_income: Optional[float] = None
    population_growth_pct: Optional[float] = None


def _try_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "").replace("$", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _try_int(value: Any) -> Optional[int]:
    f = _try_float(value)
    if f is None:
        return None
    return int(round(f))


def _normalize_header_map(row: dict[str, Any]) -> dict[str, Any]:
    return {k.strip().lower().replace(" ", "_"): v for k, v in row.items()}


class RedfinDataClient:
    """
    Redfin Data Center client.

    Notes:
    - Redfin updates downloadable exports weekly.
    - This client discovers CSV/ZIP links from the public Data Center page and
      parses rows into normalized snapshots where possible.
    """

    def __init__(self, data_center_url: str = REDFIN_DATA_CENTER_URL) -> None:
        self.data_center_url = data_center_url
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    async def discover_data_links(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            response = await client.get(self.data_center_url)
            response.raise_for_status()
            html = response.text

        links = re.findall(r'href="(https?://[^"]+\.(?:csv|zip))"', html, flags=re.IGNORECASE)
        deduped = sorted(set(links))
        return deduped

    async def download_tabular_rows(self, url: str) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.content

        lowered = url.lower()
        if lowered.endswith(".csv"):
            return self._parse_csv_bytes(payload)
        if lowered.endswith(".zip"):
            return self._parse_zip_first_csv(payload)
        return []

    @staticmethod
    def _parse_csv_bytes(payload: bytes) -> list[dict[str, str]]:
        text = payload.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    @staticmethod
    def _parse_zip_first_csv(payload: bytes) -> list[dict[str, str]]:
        with ZipFile(io.BytesIO(payload)) as zf:
            csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
            if not csv_members:
                return []
            with zf.open(csv_members[0]) as fp:
                data = fp.read()
        return RedfinDataClient._parse_csv_bytes(data)

    def parse_snapshots(
        self,
        rows: Iterable[dict[str, Any]],
        metros_of_interest: set[str],
        default_source: str = "redfin_public_data",
    ) -> list[ExtendedMarketSnapshot]:
        snapshots: list[ExtendedMarketSnapshot] = []
        for raw in rows:
            row = _normalize_header_map(raw)

            area = (
                row.get("region")
                or row.get("metro")
                or row.get("metro_area")
                or row.get("city")
                or row.get("county")
                or ""
            )
            if not area:
                continue
            if metros_of_interest and area not in metros_of_interest:
                continue

            # Redfin exports commonly use period_begin for timeseries date.
            raw_date = row.get("period_begin") or row.get("month") or row.get("date")
            if not raw_date:
                continue
            try:
                snap_date = datetime.fromisoformat(str(raw_date).replace("Z", "")).date()
            except ValueError:
                try:
                    snap_date = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    continue

            median_sale_price = _try_float(
                row.get("median_sale_price")
                or row.get("median_sale_price_usd")
                or row.get("median_list_price")
            )
            price_per_sqft = _try_float(
                row.get("median_ppsf") or row.get("price_per_sqft") or row.get("price_per_sqft_usd")
            )
            days_on_market = _try_int(
                row.get("median_days_on_market") or row.get("days_on_market")
            )
            inventory_months = _try_float(
                row.get("months_of_supply") or row.get("inventory_months")
            )

            # Rent is not always present in sale files; set conservative fallback if absent.
            median_rent = _try_float(row.get("median_rent") or row.get("median_rent_usd"))
            if median_rent is None and median_sale_price is not None:
                median_rent = round(max(1200.0, median_sale_price * 0.0045), 2)

            if (
                median_sale_price is None
                or price_per_sqft is None
                or median_rent is None
                or days_on_market is None
            ):
                continue

            snapshots.append(
                ExtendedMarketSnapshot(
                    area=area,
                    snapshot_date=snap_date,
                    median_sale_price_usd=median_sale_price,
                    price_per_sqft_usd=price_per_sqft,
                    median_rent_usd=median_rent,
                    days_on_market=days_on_market,
                    source=default_source,
                    inventory_months=inventory_months,
                )
            )
        return snapshots


class FREDClient:
    """Real FRED integration helper for free public macro series."""

    SERIES_MORTGAGE_30Y = "MORTGAGE30US"
    SERIES_HOUSING_STARTS = "HOUST"
    SERIES_CPI_SHELTER = "CUSR0000SAH1"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is required for FREDClient.")
        self._timeout = httpx.Timeout(20.0, connect=10.0)

    async def fetch_series(
        self,
        series_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[dict[str, Any]]:
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "asc",
        }
        if start_date:
            params["observation_start"] = start_date.isoformat()
        if end_date:
            params["observation_end"] = end_date.isoformat()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(FRED_API_BASE, params=params)
            response.raise_for_status()
            payload = response.json()

        observations = payload.get("observations", [])
        if not isinstance(observations, list):
            return []
        return observations

    async def latest_value(self, series_id: str) -> Optional[float]:
        observations = await self.fetch_series(series_id=series_id)
        for obs in reversed(observations):
            value = _try_float(obs.get("value"))
            if value is not None:
                return value
        return None

    async def latest_macro_snapshot(self) -> dict[str, Optional[float]]:
        mortgage, housing_starts, cpi_shelter = await asyncio.gather(
            self.latest_value(self.SERIES_MORTGAGE_30Y),
            self.latest_value(self.SERIES_HOUSING_STARTS),
            self.latest_value(self.SERIES_CPI_SHELTER),
        )
        return {
            "mortgage_rate_30y": mortgage,
            "housing_starts": housing_starts,
            "cpi_shelter_index": cpi_shelter,
        }


class CensusACSClient:
    """Census/ACS helper for income and population signals."""

    def __init__(self, api_key: Optional[str] = None, year: Optional[int] = None) -> None:
        self.api_key = api_key or os.getenv("CENSUS_API_KEY")
        self.year = year or int(os.getenv("CENSUS_ACS_YEAR", "2022"))
        self._timeout = httpx.Timeout(20.0, connect=10.0)

    async def fetch_metro_profile(self, cbsa_code: str) -> dict[str, Optional[float]]:
        # ACS 1-year profile:
        # - B19013_001E median household income
        # - B01003_001E total population
        endpoint = f"{CENSUS_ACS_BASE}/{self.year}/acs/acs1"
        params = {
            "get": "NAME,B19013_001E,B01003_001E",
            "for": f"metropolitan statistical area/micropolitan statistical area:{cbsa_code}",
        }
        if self.api_key:
            params["key"] = self.api_key

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()

        # Format: [headers, values]
        if not isinstance(data, list) or len(data) < 2:
            return {"median_household_income": None, "population": None}
        headers = data[0]
        values = data[1]
        mapping = dict(zip(headers, values))
        return {
            "median_household_income": _try_float(mapping.get("B19013_001E")),
            "population": _try_float(mapping.get("B01003_001E")),
        }


class MarketDataService:
    """
    Market data ingestion orchestrator.

    Handles:
    - weekly redfin refresh trigger
    - macro overlays from FRED
    - optional census affordability context
    - persistence to `market_snapshots`
    """

    def __init__(
        self,
        redfin_client: Optional[RedfinDataClient] = None,
        fred_client: Optional[FREDClient] = None,
        census_client: Optional[CensusACSClient] = None,
    ) -> None:
        self.redfin_client = redfin_client or RedfinDataClient()
        self.fred_client = fred_client
        self.census_client = census_client

    @staticmethod
    def should_refresh_weekly(last_refresh_at: Optional[datetime]) -> bool:
        if last_refresh_at is None:
            return True
        now = datetime.now(timezone.utc)
        return now - last_refresh_at >= timedelta(days=7)

    async def refresh_redfin_snapshots(
        self,
        db: AsyncSession,
        metros: Iterable[str],
        source_link_filter: Optional[str] = None,
    ) -> int:
        metros_set = set(metros)
        links = await self.redfin_client.discover_data_links()
        if source_link_filter:
            links = [lnk for lnk in links if source_link_filter.lower() in lnk.lower()]

        # Pick candidate links likely to contain metro-level historical pricing data.
        preferred = [
            lnk
            for lnk in links
            if any(k in lnk.lower() for k in ("metro", "market", "sale", "prices"))
        ]
        candidates = preferred[:3] if preferred else links[:2]

        merged: list[ExtendedMarketSnapshot] = []
        for link in candidates:
            rows = await self.redfin_client.download_tabular_rows(link)
            parsed = self.redfin_client.parse_snapshots(rows, metros_set, default_source=f"redfin:{link}")
            merged.extend(parsed)

        if self.fred_client and merged:
            macro = await self.fred_client.latest_macro_snapshot()
            for item in merged:
                item.mortgage_rate_30y = macro.get("mortgage_rate_30y")
                item.housing_starts = macro.get("housing_starts")
                item.cpi_shelter_index = macro.get("cpi_shelter_index")

        return await self.upsert_market_snapshots(db, merged)

    async def upsert_market_snapshots(
        self,
        db: AsyncSession,
        snapshots: Iterable[ExtendedMarketSnapshot],
    ) -> int:
        count = 0
        for snap in snapshots:
            existing_query = select(MarketSnapshotORM).where(
                MarketSnapshotORM.area == snap.area,
                MarketSnapshotORM.snapshot_date == snap.snapshot_date,
            )
            existing = (await db.execute(existing_query)).scalar_one_or_none()
            if existing:
                existing.median_sale_price_usd = snap.median_sale_price_usd
                existing.price_per_sqft_usd = snap.price_per_sqft_usd
                existing.median_rent_usd = snap.median_rent_usd
                existing.days_on_market = snap.days_on_market
                existing.source = snap.source
            else:
                db.add(
                    MarketSnapshotORM(
                        area=snap.area,
                        median_sale_price_usd=snap.median_sale_price_usd,
                        price_per_sqft_usd=snap.price_per_sqft_usd,
                        median_rent_usd=snap.median_rent_usd,
                        days_on_market=snap.days_on_market,
                        snapshot_date=snap.snapshot_date,
                        source=snap.source,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            count += 1
        await db.commit()
        return count


__all__ = [
    "ExtendedMarketSnapshot",
    "RedfinDataClient",
    "FREDClient",
    "CensusACSClient",
    "MarketDataService",
]

