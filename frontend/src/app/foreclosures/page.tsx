"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

type Foreclosure = {
  id: string;
  address: string;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  property_type: string;
  status: "pre_foreclosure" | "auction_scheduled" | "bank_owned_reo" | "hud_home";
  estimated_value_usd?: number | null;
  auction_date?: string | null;
  auction_location?: string | null;
  minimum_bid?: number | null;
  source: "hud" | "fannie_mae" | "county_records" | "public_listing";
  source_url: string;
  description: string;
  captured_at: string;
  is_active: boolean;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const statusLabel: Record<Foreclosure["status"], string> = {
  pre_foreclosure: "Pre-Foreclosure",
  auction_scheduled: "Auction",
  bank_owned_reo: "Bank-Owned REO",
  hud_home: "HUD Home",
};

const ForeclosuresMap = dynamic(() => import("./ForeclosuresMap"), { ssr: false });

function money(v?: number | null) {
  if (v == null) return "N/A";
  return `$${Math.round(v).toLocaleString()}`;
}

function countdown(auctionDate?: string | null) {
  if (!auctionDate) return "N/A";
  const ms = new Date(auctionDate).getTime() - Date.now();
  const days = Math.ceil(ms / (1000 * 60 * 60 * 24));
  if (Number.isNaN(days)) return "N/A";
  return days > 0 ? `${days} days` : "Past due";
}

export default function ForeclosuresPage() {
  const [state, setState] = useState("NJ");
  const [city, setCity] = useState("");
  const [propertyType, setPropertyType] = useState("");
  const [status, setStatus] = useState("");
  const [sortBy, setSortBy] = useState<"captured_at" | "estimated_value_usd" | "auction_date">("captured_at");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<Foreclosure[]>([]);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  async function search() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (state) params.set("state", state);
      if (city) params.set("city", city);
      if (propertyType) params.set("property_type", propertyType);
      if (status) params.set("status", status);
      const res = await fetch(`${API_BASE_URL}/api/foreclosures?${params.toString()}`);
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const json = await res.json();
      setItems(Array.isArray(json.items) ? json.items : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load foreclosures.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  async function refreshNow() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/foreclosures/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state, city: city || null }),
      });
      if (!res.ok) throw new Error(`Refresh failed (${res.status})`);
      await search();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
      setLoading(false);
    }
  }

  async function saveProperty(item: Foreclosure) {
    const email = window.prompt("Enter email to save this property:");
    if (!email) return;
    setSaveStatus("Saving...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/import/clay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: "Foreclosure Tracker Lead",
          email,
          intent: "buyer_investment",
          target_market: `${item.city || ""} ${item.state || ""}`.trim(),
          timeline: "1_3_months",
          property_type: item.property_type === "condo" ? "apartment" : item.property_type,
          financing_type: "other",
          budget_max: item.estimated_value_usd ?? undefined,
          consent_given: true,
          source: "foreclosure_tracker",
        }),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      setSaveStatus("Property saved. We will send updates.");
    } catch (err) {
      setSaveStatus(err instanceof Error ? err.message : "Could not save property.");
    }
  }

  const sortedItems = useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      if (sortBy === "estimated_value_usd") return (b.estimated_value_usd || 0) - (a.estimated_value_usd || 0);
      if (sortBy === "auction_date") return new Date(a.auction_date || 0).getTime() - new Date(b.auction_date || 0).getTime();
      return new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime();
    });
    return arr;
  }, [items, sortBy]);

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-7xl space-y-4">
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Foreclosures & Auctions Tracker</h1>
          <p className="mt-1 text-sm text-slate-600">Track HUD homes, HomePath REOs, county auctions, and public notices.</p>
          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-6">
            <input value={state} onChange={(e) => setState(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="State (NJ)" />
            <input value={city} onChange={(e) => setCity(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="City (optional)" />
            <select value={propertyType} onChange={(e) => setPropertyType(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-2 text-sm">
              <option value="">All property types</option>
              <option value="single_family">Single-family</option>
              <option value="condo">Condo</option>
              <option value="multi_family">Multi-family</option>
              <option value="land">Land</option>
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-2 text-sm">
              <option value="">All statuses</option>
              <option value="pre_foreclosure">Pre-Foreclosure</option>
              <option value="auction_scheduled">Auction</option>
              <option value="bank_owned_reo">Bank-Owned REO</option>
              <option value="hud_home">HUD Home</option>
            </select>
            <button onClick={search} className="h-10 rounded-lg bg-[#1B2A4A] px-4 text-sm font-medium text-white hover:bg-[#2E75B6]">Search</button>
            <button onClick={refreshNow} className="h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50">Refresh Data</button>
          </div>
          {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
          {saveStatus && <p className="mt-2 text-sm text-slate-600">{saveStatus}</p>}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <div className="mb-2 text-sm font-semibold text-[#1B2A4A]">Map View</div>
          <div className="h-[360px] overflow-hidden rounded-lg border border-slate-200">
            <ForeclosuresMap
              items={sortedItems.map((item) => ({
                id: item.id,
                address: item.address,
                status: statusLabel[item.status],
                estimated_value_usd: item.estimated_value_usd,
              }))}
            />
          </div>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-[#1B2A4A]">List View</h2>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as any)} className="h-9 rounded-lg border border-slate-300 px-2 text-sm">
              <option value="captured_at">Newest</option>
              <option value="estimated_value_usd">Highest value</option>
              <option value="auction_date">Auction soonest</option>
            </select>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1100px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">Address</th><th>Type</th><th>Status</th><th>Est. Value</th><th>Min Bid</th><th>Discount</th><th>Auction</th><th>Source</th><th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => <tr key={i}><td colSpan={9} className="py-3"><div className="h-8 animate-pulse rounded bg-slate-100" /></td></tr>)
                ) : sortedItems.length === 0 ? (
                  <tr><td colSpan={9} className="py-6 text-center text-slate-500">No properties found. Search and refresh to populate results.</td></tr>
                ) : (
                  sortedItems.map((item) => {
                    const discount = item.estimated_value_usd && item.minimum_bid ? ((item.estimated_value_usd - item.minimum_bid) / item.estimated_value_usd) * 100 : null;
                    const context = `Investment analysis requested for:\n${item.address}\nStatus: ${statusLabel[item.status]}\nEstimated value: ${money(item.estimated_value_usd)}\nMinimum bid: ${money(item.minimum_bid)}\nSource: ${item.source_url}\nNotes: ${item.description}`;
                    return (
                      <tr key={item.id} className="border-b border-slate-100">
                        <td className="py-2">{item.address}<div className="text-xs text-slate-500">{item.city}, {item.state} {item.zip || ""}</div></td>
                        <td>{item.property_type}</td>
                        <td><span className="rounded-full bg-slate-100 px-2 py-1 text-xs">{statusLabel[item.status]}</span></td>
                        <td>{money(item.estimated_value_usd)}</td>
                        <td>{money(item.minimum_bid)}</td>
                        <td>{discount != null ? `${discount.toFixed(1)}%` : "N/A"}</td>
                        <td><div>{item.auction_date ? new Date(item.auction_date).toLocaleDateString() : "N/A"}</div><div className="text-xs text-slate-500">{countdown(item.auction_date)}</div></td>
                        <td><a href={item.source_url} target="_blank" rel="noreferrer" className="text-[#2E75B6] hover:underline">{item.source}</a></td>
                        <td>
                          <div className="flex gap-2">
                            <a href={`/chat?prefill=${encodeURIComponent(context)}`} className="rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50">Get Investment Analysis</a>
                            <button onClick={() => saveProperty(item)} className="rounded-lg bg-[#2E75B6] px-2 py-1 text-xs text-white hover:bg-[#1B2A4A]">Save Property</button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

