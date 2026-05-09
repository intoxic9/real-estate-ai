from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Query

from ...services.listing_scraper_service import ListingScraperService

router = APIRouter(prefix="/api/scraper", tags=["scraper"])

# In-memory job storage (upgrade to DB later)
scrape_jobs: list[dict[str, Any]] = []


async def run_job(job: dict[str, Any]) -> None:
    service = ListingScraperService()
    results = await service.run_scrape_job(job["city"], job["type"])
    job["results"] = results
    job["status"] = "done"
    job["progress"] = f"{len(results)}/{len(results)}"


@router.post("/jobs")
async def launch_scrape_job(
    background_tasks: BackgroundTasks,
    city: str = Query(..., min_length=1),
    listing_type: str = Query("rent"),
) -> dict[str, Any]:
    listing_type = listing_type.lower()
    if listing_type not in {"rent", "sale"}:
        listing_type = "rent"

    job = {
        "id": len(scrape_jobs) + 1,
        "city": city.strip(),
        "type": listing_type,
        "status": "running",
        "started": datetime.utcnow().isoformat(),
        "results": [],
        "progress": "0/?",
    }
    scrape_jobs.append(job)
    background_tasks.add_task(run_job, job)
    return job


@router.get("/jobs")
async def list_jobs() -> dict[str, list[dict[str, Any]]]:
    return {"jobs": scrape_jobs}


@router.get("/listings")
async def get_listings(
    city: Optional[str] = None,
    listing_type: Optional[str] = None,
) -> dict[str, Any]:
    all_results: list[dict[str, Any]] = []
    for job in scrape_jobs:
        if job.get("status") != "done":
            continue
        for item in job.get("results", []):
            if city and str(item.get("city", "")).lower() != city.lower():
                continue
            if listing_type and item.get("listing_type") != listing_type:
                continue
            all_results.append(item)

    return {"listings": all_results, "total": len(all_results)}


__all__ = ["router"]

