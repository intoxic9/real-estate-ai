"use client";

import { FormEvent, useState } from "react";

type DealType = "price_drop" | "new_listing" | "foreclosure" | "below_market";
type DealItem = {
  id: string;
  description: string;
  source: string;
  location: string;
  price_or_value?: number | null;
  why_deal: string;
  deal_type: DealType;
  property_type: string;
  context: string;
  created_at: string;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function currency(v?: number | null) {
  if (v == null) return "N/A";
  return `$${Math.round(v).toLocaleString()}`;
}

export default function DealsPage() {
  const [city, setCity] = useState("");
  const [propertyType, setPropertyType] = useState("any");
  const [maxPrice, setMaxPrice] = useState("");
  const [dealType, setDealType] = useState<DealType>("below_market");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<DealItem[]>([]);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  async function searchDeals(e: FormEvent) {
    e.preventDefault();
    if (!city.trim()) return;
    setLoading(true);
    setError(null);
    setSaveStatus(null);
    try {
      const params = new URLSearchParams({
        city: city.trim(),
        type: dealType,
        property_type: propertyType,
      });
      if (maxPrice.trim()) params.set("max_price", maxPrice.trim());
      const res = await fetch(`${API_BASE_URL}/api/deals/search?${params.toString()}`);
      if (!res.ok) throw new Error(`Search failed (${res.status})`);
      const json = await res.json();
      setItems(Array.isArray(json.items) ? json.items : []);
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "Failed to load deals.");
    } finally {
      setLoading(false);
    }
  }

  async function saveDeal(item: DealItem) {
    const email = window.prompt("Enter email to save this deal:");
    if (!email) return;
    setSaveStatus("Saving deal...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/import/clay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: "Deal Finder Lead",
          email,
          intent: "buyer_investment",
          target_market: item.location || city,
          timeline: "1_3_months",
          property_type: propertyType === "any" ? "single_family" : propertyType,
          financing_type: "other",
          budget_max: item.price_or_value ?? undefined,
          consent_given: true,
          source: "deal_finder",
        }),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      setSaveStatus("Deal saved. We'll send similar opportunities daily.");
    } catch (err) {
      setSaveStatus(err instanceof Error ? err.message : "Could not save deal.");
    }
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-7xl space-y-4">
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Property Deal Finder</h1>
          <p className="mt-1 text-sm text-slate-600">
            Discover daily opportunities from public sources and market signals.
          </p>

          <form onSubmit={searchDeals} className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-5">
            <input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="City / State"
              className="h-10 rounded-lg border border-slate-300 px-3 text-sm md:col-span-2"
              required
            />
            <select
              value={propertyType}
              onChange={(e) => setPropertyType(e.target.value)}
              className="h-10 rounded-lg border border-slate-300 px-2 text-sm"
            >
              <option value="any">Any property type</option>
              <option value="single_family">Single family</option>
              <option value="townhouse">Townhouse</option>
              <option value="apartment">Apartment</option>
              <option value="land">Land</option>
            </select>
            <input
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
              type="number"
              min={0}
              placeholder="Max price"
              className="h-10 rounded-lg border border-slate-300 px-3 text-sm"
            />
            <select
              value={dealType}
              onChange={(e) => setDealType(e.target.value as DealType)}
              className="h-10 rounded-lg border border-slate-300 px-2 text-sm"
            >
              <option value="price_drop">Price drop</option>
              <option value="new_listing">New listing</option>
              <option value="foreclosure">Foreclosure</option>
              <option value="below_market">Below market</option>
            </select>
            <button className="h-10 rounded-lg bg-[#1B2A4A] px-4 text-sm font-medium text-white hover:bg-[#2E75B6] md:col-span-5 md:w-fit">
              Search Opportunities
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
          {saveStatus && <p className="mt-2 text-sm text-slate-600">{saveStatus}</p>}
        </section>

        <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-52 animate-pulse rounded-xl border border-slate-200 bg-white" />
              ))
            : items.map((item) => (
                <article key={item.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-xs uppercase tracking-wide text-slate-500">
                    {item.source} • {new Date(item.created_at).toLocaleDateString()}
                  </p>
                  <p className="mt-2 line-clamp-3 text-sm text-slate-800">{item.description}</p>
                  <div className="mt-3 space-y-1 text-xs text-slate-600">
                    <p>
                      <strong>Location:</strong> {item.location}
                    </p>
                    <p>
                      <strong>Price / Est. value:</strong> {currency(item.price_or_value)}
                    </p>
                    <p>
                      <strong>Why it&apos;s a deal:</strong> {item.why_deal}
                    </p>
                  </div>
                  <div className="mt-4 flex gap-2">
                    <a
                      href={`/chat?prefill=${encodeURIComponent(`Please analyze this property opportunity:\n${item.context}`)}`}
                      className="inline-flex flex-1 items-center justify-center rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-800 hover:bg-slate-50"
                    >
                      Learn More
                    </a>
                    <button
                      onClick={() => saveDeal(item)}
                      className="inline-flex flex-1 items-center justify-center rounded-lg bg-[#2E75B6] px-3 py-2 text-xs font-medium text-white hover:bg-[#1B2A4A]"
                    >
                      Save Deal
                    </button>
                  </div>
                </article>
              ))}
        </section>

        {!loading && items.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            Search a city to discover fresh opportunities.
          </div>
        )}
      </div>
    </main>
  );
}

