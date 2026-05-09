"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

type ListingItem = {
  title: string;
  description: string;
  url: string;
  source: string;
  city: string;
  listing_type: "rent" | "sale";
  scraped_at: string;
};

function extractPrice(text: string): string | null {
  const match = text.match(/\$\s?\d[\d,]*/);
  return match ? match[0].replace(/\s+/g, "") : null;
}

export default function ListingsPage() {
  const [items, setItems] = useState<ListingItem[]>([]);
  const [search, setSearch] = useState("");
  const [cityFilter, setCityFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState<"all" | "rent" | "sale">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadListings(city?: string, listingType?: string) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (city && city !== "all") params.set("city", city);
      if (listingType && listingType !== "all") params.set("listing_type", listingType);
      const url = `${API_BASE_URL}/api/scraper/listings${params.toString() ? `?${params.toString()}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Failed to load listings (${res.status})`);
      const json = (await res.json()) as { listings?: ListingItem[] };
      setItems(Array.isArray(json.listings) ? json.listings : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load listings.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadListings(cityFilter, typeFilter).catch(() => null);
  }, [cityFilter, typeFilter]);

  const cityOptions = useMemo(() => {
    const uniq = new Set(items.map((x) => x.city).filter(Boolean));
    return ["all", ...Array.from(uniq).sort()];
  }, [items]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => `${item.title} ${item.description}`.toLowerCase().includes(q));
  }, [items, search]);

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-[1400px] space-y-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Listings</h1>
          <p className="mt-1 text-xs text-slate-500">Browse results discovered by scraper jobs.</p>
        </div>

        {error && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title or description"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm md:col-span-2"
            />
            <select
              value={cityFilter}
              onChange={(e) => setCityFilter(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {cityOptions.map((city) => (
                <option key={city} value={city}>
                  {city === "all" ? "All Cities" : city}
                </option>
              ))}
            </select>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as "all" | "rent" | "sale")}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="all">All Types</option>
              <option value="rent">For Rent</option>
              <option value="sale">For Sale</option>
            </select>
          </div>
        </section>

        {loading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-48 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">No listings found.</div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((item, idx) => {
              const price = extractPrice(`${item.title} ${item.description}`);
              return (
                <article key={`${item.url}-${idx}`} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="line-clamp-2 text-sm font-semibold text-[#1B2A4A]">{item.title || "Untitled listing"}</h2>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">{item.source}</span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <span className={`rounded-full px-2 py-1 ${item.listing_type === "rent" ? "bg-emerald-100 text-emerald-700" : "bg-indigo-100 text-indigo-700"}`}>
                      {item.listing_type}
                    </span>
                    <span className="rounded-full bg-blue-100 px-2 py-1 text-blue-700">{item.city}</span>
                    {price && <span className="rounded-full bg-amber-100 px-2 py-1 text-amber-700">{price}</span>}
                  </div>
                  <p className="mt-3 line-clamp-4 text-xs leading-relaxed text-slate-600">{item.description || "No description available."}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium text-[#2E75B6] hover:underline"
                    >
                      View
                    </a>
                    <span className="text-[11px] text-slate-400">{new Date(item.scraped_at).toLocaleString()}</span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}

