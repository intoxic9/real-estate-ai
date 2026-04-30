"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const CITIES = [
  "New York",
  "Jersey City",
  "Austin",
  "Miami",
  "Denver",
  "Seattle",
  "Phoenix",
  "Chicago",
  "San Francisco",
  "Atlanta",
];

type ScrapeJob = {
  id: number;
  city: string;
  type: "rent" | "sale";
  status: "running" | "done";
  progress: string;
  started: string;
  results: unknown[];
};

export default function ScraperPage() {
  const [citySelect, setCitySelect] = useState(CITIES[0]);
  const [customCity, setCustomCity] = useState("");
  const [listingType, setListingType] = useState<"rent" | "sale">("rent");
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const city = useMemo(() => (customCity.trim() ? customCity.trim() : citySelect), [citySelect, customCity]);

  async function loadJobs() {
    const res = await fetch(`${API_BASE_URL}/api/scraper/jobs`);
    if (!res.ok) throw new Error(`Failed to load jobs (${res.status})`);
    const json = (await res.json()) as { jobs?: ScrapeJob[] };
    setJobs(Array.isArray(json.jobs) ? json.jobs : []);
  }

  useEffect(() => {
    loadJobs().catch(() => null);
  }, []);

  async function launchScrapeJob(e: FormEvent) {
    e.preventDefault();
    if (!city) return;
    setLoading(true);
    setError(null);
    try {
      const url = `${API_BASE_URL}/api/scraper/jobs?city=${encodeURIComponent(city)}&listing_type=${listingType}`;
      const res = await fetch(url, { method: "POST" });
      if (!res.ok) throw new Error(`Launch failed (${res.status})`);
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not launch scrape job.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-[1400px] space-y-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Scraper</h1>
          <p className="mt-1 text-xs text-slate-500">
            Launch DuckDuckGo-powered listing discovery jobs for rent/sale signals.
          </p>
        </div>

        {error && <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <form onSubmit={launchScrapeJob} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm xl:col-span-1">
            <h2 className="text-sm font-semibold text-slate-800">New Scrape Job</h2>

            <label className="mt-4 block text-xs font-medium text-slate-600">City</label>
            <select
              value={citySelect}
              onChange={(e) => setCitySelect(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {CITIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <label className="mt-3 block text-xs font-medium text-slate-600">Custom city (optional)</label>
            <input
              value={customCity}
              onChange={(e) => setCustomCity(e.target.value)}
              placeholder="Enter city name"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />

            <label className="mt-3 block text-xs font-medium text-slate-600">Listing type</label>
            <div className="mt-1 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setListingType("rent")}
                className={`rounded-lg border px-3 py-2 text-sm ${listingType === "rent" ? "border-[#2E75B6] bg-blue-50 text-[#1B2A4A]" : "border-slate-300"}`}
              >
                For Rent
              </button>
              <button
                type="button"
                onClick={() => setListingType("sale")}
                className={`rounded-lg border px-3 py-2 text-sm ${listingType === "sale" ? "border-[#2E75B6] bg-blue-50 text-[#1B2A4A]" : "border-slate-300"}`}
              >
                For Sale
              </button>
            </div>

            <button
              type="submit"
              disabled={loading || !city}
              className="mt-4 w-full rounded-lg bg-amber-400 px-3 py-2 text-sm font-semibold text-[#1B2A4A] hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Launching..." : "Launch Scrape Job"}
            </button>
          </form>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm xl:col-span-2">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Job History</h2>
              <button onClick={() => loadJobs()} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50">
                Refresh
              </button>
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="py-2">#</th>
                    <th>City</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length === 0 ? (
                    <tr>
                      <td className="py-4 text-slate-500" colSpan={6}>
                        No scrape jobs yet.
                      </td>
                    </tr>
                  ) : (
                    jobs
                      .slice()
                      .reverse()
                      .map((job) => (
                        <tr key={job.id} className="border-b border-slate-100">
                          <td className="py-2">{job.id}</td>
                          <td>{job.city}</td>
                          <td>
                            <span className={`rounded-full px-2 py-1 text-xs ${job.type === "rent" ? "bg-emerald-100 text-emerald-700" : "bg-indigo-100 text-indigo-700"}`}>
                              {job.type}
                            </span>
                          </td>
                          <td>
                            <span className={`rounded-full px-2 py-1 text-xs ${job.status === "done" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700"}`}>
                              {job.status}
                            </span>
                          </td>
                          <td>{job.progress}</td>
                          <td>{new Date(job.started).toLocaleString()}</td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

