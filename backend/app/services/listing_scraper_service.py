from __future__ import annotations

from datetime import datetime
from typing import Any

from ddgs import DDGS


class ListingScraperService:
    SEARCH_TEMPLATES = {
        "rent": "{city} apartments for rent",
        "sale": "{city} homes for sale",
    }

    async def run_scrape_job(self, city: str, listing_type: str = "rent") -> list[dict[str, Any]]:
        """Search listings using DuckDuckGo text search results."""
        query = self.SEARCH_TEMPLATES.get(listing_type, self.SEARCH_TEMPLATES["rent"]).format(city=city)
        results: list[dict[str, Any]] = []
        try:
            raw = list(DDGS().text(query, max_results=20))
            for item in raw:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "description": item.get("body", ""),
                        "url": item.get("href", ""),
                        "source": "duckduckgo",
                        "city": city,
                        "listing_type": listing_type,
                        "scraped_at": datetime.utcnow().isoformat(),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            print(f"Scrape error: {exc}")
        return results

