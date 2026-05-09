from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_groq import ChatGroq

from ...core.config import GROQ_API_KEY_SEARCH
from ...core.database import get_db
from ...core.schemas import MarketSnapshotORM

router = APIRouter(prefix="/api/mortgage", tags=["mortgage"])


class MortgageCalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annual_income: float = Field(gt=0)
    monthly_debts: float = Field(ge=0)
    down_payment: float = Field(ge=0)
    credit_score_range: str
    target_cities: list[str] = Field(default_factory=list)


class PaymentBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_interest: float
    taxes: float
    insurance: float
    total_monthly: float


class LoanComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_type: Literal["fha", "conventional", "va"]
    dti_limit: float
    min_down_percent: float
    pmi_included: bool
    min_credit_score: int
    max_home_price: float
    monthly_payment: PaymentBreakdown


class CityAffordability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str
    median_home_price: float
    affordability_percent_of_market: float
    message: str


class MortgageCalculateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_home_price: float
    monthly_payment_breakdown: PaymentBreakdown
    mortgage_rate_30y: float
    loan_comparisons: list[LoanComparison]
    city_affordability_map: list[CityAffordability]
    ai_recommendation: str
    disclaimers: list[str]


async def _fetch_mortgage_rate() -> float:
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return 6.75
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "MORTGAGE30US",
                    "api_key": key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
            )
            res.raise_for_status()
            rows = res.json().get("observations", [])
            if rows:
                return float(rows[0].get("value"))
    except Exception:
        return 6.75
    return 6.75


def _max_loan_from_payment(max_monthly_payment: float, annual_rate_pct: float, years: int = 30) -> float:
    r = (annual_rate_pct / 100.0) / 12.0
    n = years * 12
    if r <= 0:
        return max_monthly_payment * n
    return max_monthly_payment * (((1 + r) ** n - 1) / (r * (1 + r) ** n))


def _payment_components(home_price: float, down_percent: float, rate: float, include_pmi: bool) -> PaymentBreakdown:
    loan = max(home_price * (1 - down_percent), 0)
    monthly_pi = home_price if home_price <= 0 else (loan / max(_max_loan_from_payment(1, rate), 1))
    # Use stable blended assumptions for taxes/insurance and optional PMI.
    taxes = (home_price * 0.012) / 12.0
    insurance = (home_price * 0.0045) / 12.0
    pmi = (home_price * 0.007) / 12.0 if include_pmi else 0.0
    total = monthly_pi + taxes + insurance + pmi
    return PaymentBreakdown(
        principal_interest=round(monthly_pi, 2),
        taxes=round(taxes, 2),
        insurance=round(insurance + pmi, 2),
        total_monthly=round(total, 2),
    )


@router.post("/calculate", response_model=MortgageCalculateResponse, status_code=status.HTTP_200_OK)
async def calculate_mortgage(
    payload: MortgageCalculateRequest,
    db: AsyncSession = Depends(get_db),
) -> MortgageCalculateResponse:
    rate = await _fetch_mortgage_rate()

    conventional_max_payment = max((payload.annual_income / 12.0) * 0.43 - payload.monthly_debts, 0)
    fha_max_payment = max((payload.annual_income / 12.0) * 0.50 - payload.monthly_debts, 0)
    va_max_payment = conventional_max_payment

    conventional_loan = _max_loan_from_payment(conventional_max_payment, rate)
    fha_loan = _max_loan_from_payment(fha_max_payment, rate)
    va_loan = _max_loan_from_payment(va_max_payment, rate)

    conventional_price = conventional_loan + payload.down_payment
    fha_price = (fha_loan + payload.down_payment) / 0.965 if payload.down_payment > 0 else fha_loan / 0.965
    va_price = va_loan + payload.down_payment

    loan_comparisons = [
        LoanComparison(
            loan_type="fha",
            dti_limit=0.50,
            min_down_percent=0.035,
            pmi_included=True,
            min_credit_score=580,
            max_home_price=round(max(fha_price, 0), 2),
            monthly_payment=_payment_components(max(fha_price, 0), 0.035, rate, include_pmi=True),
        ),
        LoanComparison(
            loan_type="conventional",
            dti_limit=0.43,
            min_down_percent=0.05,
            pmi_included=True,
            min_credit_score=620,
            max_home_price=round(max(conventional_price, 0), 2),
            monthly_payment=_payment_components(max(conventional_price, 0), 0.05, rate, include_pmi=True),
        ),
        LoanComparison(
            loan_type="va",
            dti_limit=0.43,
            min_down_percent=0.0,
            pmi_included=False,
            min_credit_score=580,
            max_home_price=round(max(va_price, 0), 2),
            monthly_payment=_payment_components(max(va_price, 0), 0.0, rate, include_pmi=False),
        ),
    ]

    max_home_price = round(max(conventional_price, 0), 2)
    monthly_payment_breakdown = _payment_components(max_home_price, 0.05, rate, include_pmi=True)

    city_affordability_map: list[CityAffordability] = []
    for city in payload.target_cities:
        city_norm = city.strip().lower()
        if not city_norm:
            continue
        row = (
            await db.execute(
                select(MarketSnapshotORM)
                .where(func.lower(MarketSnapshotORM.area) == city_norm)
                .order_by(desc(MarketSnapshotORM.snapshot_date), desc(MarketSnapshotORM.created_at))
                .limit(1)
            )
        ).scalars().first()
        median = float(row.median_sale_price_usd) if row else 0.0
        if median <= 0:
            continue
        pct = round(min((max_home_price / median) * 100.0, 100.0), 1)
        message = f"You can afford about {pct}% of homes in {row.area if row else city}."
        city_affordability_map.append(
            CityAffordability(
                city=row.area if row else city,
                median_home_price=median,
                affordability_percent_of_market=pct,
                message=message,
            )
        )

    ai_recommendation = (
        "Based on your income, debt, and down payment, you may fit best in a conventional or FHA path. "
        "Focus on cities where your affordability exceeds 80% and keep total DTI below program limits."
    )
    api_key = (GROQ_API_KEY_SEARCH or os.getenv("GROQ_API_KEY", "")).strip()
    if api_key:
        try:
            model_name = os.getenv("MORTGAGE_MODEL", "llama-3.1-8b-instant")
            llm = ChatGroq(api_key=api_key, model=model_name, temperature=0.3)
            prompt = (
                "You are a mortgage advisor assistant. Provide a concise, practical recommendation in 3-4 sentences.\n"
                f"Annual income: {payload.annual_income}\n"
                f"Monthly debts: {payload.monthly_debts}\n"
                f"Down payment: {payload.down_payment}\n"
                f"Credit score range: {payload.credit_score_range}\n"
                f"Max conventional price: {max_home_price}\n"
                f"City affordability: {[c.model_dump() for c in city_affordability_map]}"
            )
            out = await llm.ainvoke(prompt)
            text = getattr(out, "content", None)
            if isinstance(text, str) and text.strip():
                ai_recommendation = text.strip()
        except Exception:
            pass

    disclaimers = [
        "This is an estimate, not a pre-approval.",
        "Consult a licensed mortgage broker for actual rates and terms.",
        "We do not store your financial information.",
    ]

    return MortgageCalculateResponse(
        max_home_price=max_home_price,
        monthly_payment_breakdown=monthly_payment_breakdown,
        mortgage_rate_30y=round(rate, 2),
        loan_comparisons=loan_comparisons,
        city_affordability_map=city_affordability_map,
        ai_recommendation=ai_recommendation,
        disclaimers=disclaimers,
    )

