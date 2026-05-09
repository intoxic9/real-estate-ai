from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import AsyncSessionLocal


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM market_snapshots WHERE area LIKE '%Dubai%'"))
        await db.commit()
        remaining = (
            await db.execute(text("SELECT count(1) FROM market_snapshots WHERE area LIKE '%Dubai%'"))
        ).scalar_one()
    print(f"dubai_rows_remaining={remaining}")


if __name__ == "__main__":
    asyncio.run(main())
