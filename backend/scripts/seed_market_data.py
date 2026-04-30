"""
Seed realistic US metro market snapshot data.

Usage:
    python scripts/seed_market_data.py
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import sys

from sqlalchemy import select, text

# Allow running this script directly via `python scripts/seed_market_data.py`
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.schemas import MarketSnapshotORM  # noqa: E402


@dataclass(frozen=True)
class MetroSeedConfig:
    metro: str
    median_price: float
    median_rent: float
    price_per_sqft: float
    days_on_market: int
    inventory_months: float


METRO_CONFIGS: list[MetroSeedConfig] = [
    MetroSeedConfig("New York Metro", 650000, 3200, 550, 35, 3.2),
    MetroSeedConfig("Los Angeles", 850000, 2800, 600, 33, 2.8),
    MetroSeedConfig("Miami", 550000, 2500, 450, 36, 4.1),
    MetroSeedConfig("Chicago", 330000, 1800, 250, 40, 4.8),
    MetroSeedConfig("Dallas-Fort Worth", 380000, 1700, 200, 34, 4.4),
    MetroSeedConfig("Austin", 450000, 1600, 280, 38, 4.0),
    MetroSeedConfig("Denver", 550000, 1900, 350, 32, 3.5),
    MetroSeedConfig("Seattle", 750000, 2400, 480, 30, 2.9),
    MetroSeedConfig("Phoenix", 420000, 1500, 270, 37, 4.5),
    MetroSeedConfig("Atlanta", 370000, 1600, 220, 39, 4.7),
    MetroSeedConfig("Nashville", 430000, 1700, 290, 35, 4.3),
    MetroSeedConfig("Charlotte", 380000, 1500, 230, 36, 4.6),
    MetroSeedConfig("Tampa", 370000, 1800, 260, 41, 5.0),
    MetroSeedConfig("Raleigh", 400000, 1500, 240, 34, 4.2),
    MetroSeedConfig("San Francisco", 1200000, 3500, 900, 25, 2.3),
    MetroSeedConfig("Boston", 680000, 2800, 500, 31, 3.1),
]


def month_sequence(months_back: int = 24) -> list[date]:
    today = date.today()
    year = today.year
    month = today.month
    seq: list[date] = []
    for _ in range(months_back):
        seq.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return sorted(seq)


def with_fluctuation(base: float, low: float = -0.03, high: float = 0.03) -> float:
    return base * (1 + random.uniform(low, high))


async def seed() -> None:
    random.seed(8102026)
    months = month_sequence(months_back=24)
    now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0

    async with AsyncSessionLocal() as db:
        await _ensure_market_schema(db)

        for metro in METRO_CONFIGS:
            price = metro.median_price
            rent = metro.median_rent
            ppsf = metro.price_per_sqft
            dom = metro.days_on_market
            inventory = metro.inventory_months

            for snap_date in months:
                # Gradual trend + monthly noise.
                price = with_fluctuation(price, -0.02, 0.03)
                rent = with_fluctuation(rent, -0.015, 0.02)
                ppsf = with_fluctuation(ppsf, -0.02, 0.03)
                dom = max(18, int(round(with_fluctuation(float(dom), -0.08, 0.08))))
                inventory = max(1.5, min(7.5, with_fluctuation(inventory, -0.1, 0.1)))

                # Current schema does not yet include inventory as a dedicated column.
                # Keep it in source metadata string so seed context remains auditable.
                source = f"seed_us_markets_v1|inventory={inventory:.2f}m"

                existing_query = select(MarketSnapshotORM).where(
                    MarketSnapshotORM.area == metro.metro,
                    MarketSnapshotORM.snapshot_date == snap_date,
                )
                existing = (await db.execute(existing_query)).scalar_one_or_none()
                if existing:
                    existing.median_sale_price_usd = round(price, 2)
                    existing.median_rent_usd = round(rent, 2)
                    existing.price_per_sqft_usd = round(ppsf, 2)
                    existing.days_on_market = dom
                    existing.source = source
                    updated += 1
                else:
                    db.add(
                        MarketSnapshotORM(
                            area=metro.metro,
                            median_sale_price_usd=round(price, 2),
                            price_per_sqft_usd=round(ppsf, 2),
                            median_rent_usd=round(rent, 2),
                            days_on_market=dom,
                            snapshot_date=snap_date,
                            source=source,
                            created_at=now,
                        )
                    )
                    inserted += 1

        await db.commit()

    print(
        f"Market seed complete. inserted={inserted}, updated={updated}, "
        f"metros={len(METRO_CONFIGS)}, months={len(months)}"
    )


async def _ensure_market_schema(db) -> None:
    """
    Align older market schema variants (AED column names) with USD model fields.
    """
    await db.execute(
        text(
            "ALTER TABLE market_snapshots "
            "ADD COLUMN IF NOT EXISTS median_sale_price_usd DOUBLE PRECISION"
        )
    )
    await db.execute(
        text(
            "ALTER TABLE market_snapshots "
            "ADD COLUMN IF NOT EXISTS price_per_sqft_usd DOUBLE PRECISION"
        )
    )
    await db.execute(
        text(
            "ALTER TABLE market_snapshots "
            "ADD COLUMN IF NOT EXISTS median_rent_usd DOUBLE PRECISION"
        )
    )

    # Backfill from legacy AED columns if present.
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='median_sale_price_aed') THEN "
            "UPDATE market_snapshots SET median_sale_price_usd = COALESCE(median_sale_price_usd, median_sale_price_aed); "
            "END IF; "
            "END $$;"
        )
    )
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='price_per_sqft_aed') THEN "
            "UPDATE market_snapshots SET price_per_sqft_usd = COALESCE(price_per_sqft_usd, price_per_sqft_aed); "
            "END IF; "
            "END $$;"
        )
    )
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='median_rent_aed') THEN "
            "UPDATE market_snapshots SET median_rent_usd = COALESCE(median_rent_usd, median_rent_aed); "
            "END IF; "
            "END $$;"
        )
    )

    # Legacy AED columns may still have NOT NULL constraints, which breaks inserts
    # now that the ORM writes USD fields. Relax constraints if legacy columns exist.
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='median_sale_price_aed') THEN "
            "ALTER TABLE market_snapshots ALTER COLUMN median_sale_price_aed DROP NOT NULL; "
            "END IF; "
            "END $$;"
        )
    )
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='price_per_sqft_aed') THEN "
            "ALTER TABLE market_snapshots ALTER COLUMN price_per_sqft_aed DROP NOT NULL; "
            "END IF; "
            "END $$;"
        )
    )
    await db.execute(
        text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='market_snapshots' AND column_name='median_rent_aed') THEN "
            "ALTER TABLE market_snapshots ALTER COLUMN median_rent_aed DROP NOT NULL; "
            "END IF; "
            "END $$;"
        )
    )
    await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())

