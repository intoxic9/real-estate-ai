"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Building2, Mail, TrendingUp } from "lucide-react";

type SimilarArea = {
  area: string;
  median_home_price: number;
  relative_to_selected_pct: number;
};

type Report = {
  area: string;
  median_home_price: number;
  home_price_trend_pct: number;
  median_rent: number;
  rent_trend_pct: number;
  price_per_sqft: number;
  metro_avg_price_per_sqft: number;
  price_per_sqft_vs_metro_pct: number;
  days_on_market: number;
  inventory_months: number;
  market_side: "buyers" | "balanced" | "sellers";
  mortgage_rate_30y: number;
  estimated_monthly_payment: number;
  market_summary: string;
  best_for_tags: string[];
  price_forecast: "trending_up" | "stable" | "cooling";
  similar_areas: SimilarArea[];
  generated_at: string;
};

type MarketArea = {
  area: string;
};

type AreaMeta = {
  state: string;
  city: string;
  area: string;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const AREA_STATE_MAP: Record<string, string> = {
  Atlanta: "GA",
  Austin: "TX",
  Boston: "MA",
  Charlotte: "NC",
  Chicago: "IL",
  "Dallas-Fort Worth": "TX",
  Denver: "CO",
  "Los Angeles": "CA",
  Miami: "FL",
  Nashville: "TN",
  "New York Metro": "NY",
  Phoenix: "AZ",
  Raleigh: "NC",
  "San Francisco": "CA",
  Seattle: "WA",
  Tampa: "FL",
};

function money(v: number) {
  return `$${Math.round(v).toLocaleString()}`;
}

function Trend({ value }: { value: number }) {
  const up = value >= 0;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${up ? "text-emerald-600" : "text-rose-600"}`}>
      {up ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}
      {up ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

export default function NeighborhoodPage() {
  const [queryArea, setQueryArea] = useState("");
  const [availableAreas, setAvailableAreas] = useState<string[]>([]);
  const [selectedState, setSelectedState] = useState("");
  const [selectedCity, setSelectedCity] = useState("");
  const [areasLoading, setAreasLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  const [email, setEmail] = useState("");
  const [emailStatus, setEmailStatus] = useState<string | null>(null);

  useEffect(() => {
    if (availableAreas.length || areasLoading) return;
    setAreasLoading(true);
    fetch(`${API_BASE_URL}/api/market/areas`)
      .then((res) => (res.ok ? res.json() : []))
      .then((rows: MarketArea[]) => {
        const areas = Array.isArray(rows) ? rows.map((r) => r.area).filter(Boolean) : [];
        setAvailableAreas(areas);
        if (!queryArea && areas.length) {
          setQueryArea(areas[0]);
        }
      })
      .catch(() => {
        setAvailableAreas([]);
      })
      .finally(() => setAreasLoading(false));
  }, [availableAreas.length, areasLoading, queryArea]);

  const maxComparePrice = useMemo(() => {
    if (!report?.similar_areas.length) return 1;
    return Math.max(...report.similar_areas.map((a) => a.median_home_price), report.median_home_price);
  }, [report]);

  const areaMeta = useMemo<AreaMeta[]>(
    () =>
      availableAreas.map((area) => ({
        area,
        state: AREA_STATE_MAP[area] || "Other",
        city: area.replace(/\s+Metro$/i, ""),
      })),
    [availableAreas]
  );

  const states = useMemo(
    () => Array.from(new Set(areaMeta.map((a) => a.state))).sort(),
    [areaMeta]
  );

  const cities = useMemo(
    () =>
      Array.from(
        new Set(
          areaMeta
            .filter((a) => (selectedState ? a.state === selectedState : true))
            .map((a) => a.city)
        )
      ).sort(),
    [areaMeta, selectedState]
  );

  const filteredAreas = useMemo(
    () =>
      areaMeta
        .filter((a) => (selectedState ? a.state === selectedState : true))
        .filter((a) => (selectedCity ? a.city === selectedCity : true))
        .map((a) => a.area),
    [areaMeta, selectedState, selectedCity]
  );

  useEffect(() => {
    if (!areaMeta.length) return;
    if (!selectedState) {
      setSelectedState(areaMeta[0].state);
      return;
    }
    if (!selectedCity) {
      const firstCity = areaMeta.find((a) => a.state === selectedState)?.city;
      if (firstCity) setSelectedCity(firstCity);
      return;
    }
    if (!queryArea) {
      const firstArea = areaMeta.find((a) => a.state === selectedState && a.city === selectedCity)?.area;
      if (firstArea) setQueryArea(firstArea);
    }
  }, [areaMeta, selectedState, selectedCity, queryArea]);

  async function fetchReport(e: FormEvent) {
    e.preventDefault();
    if (!queryArea.trim()) return;
    setLoading(true);
    setError(null);
    setEmailStatus(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/neighborhood/report?area=${encodeURIComponent(queryArea.trim())}`);
      if (!res.ok) {
        throw new Error(`Unable to generate report (${res.status})`);
      }
      const data = (await res.json()) as Report;
      setReport(data);
    } catch (err) {
      setReport(null);
      setError(err instanceof Error ? err.message : "Failed to load report.");
    } finally {
      setLoading(false);
    }
  }

  async function captureEmail(e: FormEvent) {
    e.preventDefault();
    if (!report || !email.trim()) return;
    setEmailStatus("Saving...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/import/clay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: "Neighborhood Report Lead",
          email: email.trim(),
          intent: "buyer_primary",
          target_market: report.area,
          timeline: "3_6_months",
          property_type: "single_family",
          financing_type: "unknown",
          consent_given: true,
          source: "neighborhood_report",
        }),
      });
      if (!res.ok) throw new Error(`Lead capture failed (${res.status})`);
      setEmailStatus("Report request saved. We'll follow up shortly.");
    } catch (err) {
      setEmailStatus(err instanceof Error ? err.message : "Unable to submit email.");
    }
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Free Neighborhood Intelligence Report</h1>
          <p className="mt-1 text-sm text-slate-600">
            Get market trends, affordability signals, and AI-generated insights for any neighborhood.
          </p>
          <form onSubmit={fetchReport} className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-4">
            <select
              value={selectedState}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedState(val);
                setSelectedCity("");
                setQueryArea("");
              }}
              className="h-11 rounded-lg border border-slate-300 px-3 text-sm"
            >
              <option value="">{areasLoading ? "Loading states..." : "Select state"}</option>
              {states.map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>

            <select
              value={selectedCity}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedCity(val);
                setQueryArea("");
              }}
              className="h-11 rounded-lg border border-slate-300 px-3 text-sm"
              disabled={!selectedState}
            >
              <option value="">{selectedState ? "Select city" : "Select state first"}</option>
              {cities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
            </select>

            <select
              value={queryArea}
              onChange={(e) => setQueryArea(e.target.value)}
              className="h-11 rounded-lg border border-slate-300 px-3 text-sm"
              required
              disabled={!selectedCity}
            >
              <option value="" disabled>
                {selectedCity ? "Select an area" : "Select city first"}
              </option>
              {filteredAreas.map((area) => (
                <option key={area} value={area}>
                  {area}
                </option>
              ))}
            </select>
            <button
              className="h-11 rounded-lg bg-[#1B2A4A] px-4 text-sm font-medium text-white hover:bg-[#2E75B6]"
            >
              Generate Report
            </button>
          </form>
          {loading && <p className="mt-3 text-sm text-slate-500">Building your neighborhood report...</p>}
          {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
        </section>

        {report && (
          <section className="grid grid-cols-1 gap-5 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-5">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-[#1B2A4A]">{report.area} Market Data</h2>
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Median Home Price</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{money(report.median_home_price)}</p>
                    <Trend value={report.home_price_trend_pct} />
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Median Rent</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{money(report.median_rent)}</p>
                    <Trend value={report.rent_trend_pct} />
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Price / Sq Ft</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">${report.price_per_sqft.toLocaleString()}</p>
                    <p className="text-xs text-slate-600">
                      Metro avg: ${report.metro_avg_price_per_sqft.toLocaleString()} ({report.price_per_sqft_vs_metro_pct >= 0 ? "+" : ""}
                      {report.price_per_sqft_vs_metro_pct.toFixed(2)}%)
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Days on Market</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{report.days_on_market} days</p>
                    <p className="text-xs text-slate-600">How fast homes are selling</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Inventory</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{report.inventory_months} months</p>
                    <p className="text-xs text-slate-600 capitalize">{report.market_side} market</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Mortgage Affordability</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{money(report.estimated_monthly_payment)}/mo</p>
                    <p className="text-xs text-slate-600">At {report.mortgage_rate_30y}% (30y fixed)</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="text-base font-semibold text-[#1B2A4A]">AI-Generated Insights</h3>
                <p className="mt-3 text-sm leading-6 text-slate-700">{report.market_summary}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {report.best_for_tags.map((tag) => (
                    <span key={tag} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">
                      {tag}
                    </span>
                  ))}
                </div>
                <div className="mt-3 inline-flex items-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
                  <TrendingUp className="h-4 w-4" />
                  Price forecast:{" "}
                  <strong>
                    {report.price_forecast === "trending_up"
                      ? "Trending up"
                      : report.price_forecast === "cooling"
                      ? "Cooling"
                      : "Stable"}
                  </strong>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="text-base font-semibold text-[#1B2A4A]">Compare to Similar Areas</h3>
                <div className="mt-3 space-y-3">
                  {report.similar_areas.map((area) => {
                    const width = Math.max(15, Math.round((area.median_home_price / maxComparePrice) * 100));
                    return (
                      <div key={area.area}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="font-medium text-slate-700">{area.area}</span>
                          <span className="text-slate-600">
                            {money(area.median_home_price)} ({area.relative_to_selected_pct >= 0 ? "+" : ""}
                            {area.relative_to_selected_pct.toFixed(1)}%)
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-slate-100">
                          <div className="h-2 rounded-full bg-[#2E75B6]" style={{ width: `${width}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="space-y-5">
              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="text-base font-semibold text-[#1B2A4A]">Next Step</h3>
                <p className="mt-2 text-sm text-slate-600">
                  Want to explore homes in {report.area}? Chat with our AI assistant.
                </p>
                <a
                  href="/chat"
                  className="mt-3 inline-flex w-full items-center justify-center rounded-lg bg-[#1B2A4A] px-4 py-2 text-sm font-medium text-white hover:bg-[#2E75B6]"
                >
                  Chat with AI Assistant
                </a>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="flex items-center gap-2 text-base font-semibold text-[#1B2A4A]">
                  <Mail className="h-4 w-4" />
                  Get this report emailed to you
                </h3>
                <form onSubmit={captureEmail} className="mt-3 space-y-2">
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    type="email"
                    required
                    placeholder="you@email.com"
                    className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm"
                  />
                  <button className="h-10 w-full rounded-lg bg-[#2E75B6] text-sm font-medium text-white hover:bg-[#1B2A4A]">
                    Email My Report
                  </button>
                </form>
                {emailStatus && <p className="mt-2 text-xs text-slate-600">{emailStatus}</p>}
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="flex items-center gap-2 text-xs text-slate-600">
                  <Building2 className="h-3.5 w-3.5" />
                  Generated {new Date(report.generated_at).toLocaleString()}
                </p>
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

