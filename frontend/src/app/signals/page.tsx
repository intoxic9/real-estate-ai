"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

type SignalSource = "reddit_api" | "reddit_rss" | "twitter" | "twitter_google" | "google_alerts";
type IntentLevel = "strong_intent" | "moderate_intent" | "weak_intent" | "not_relevant";

type LeadSignal = {
  id: string;
  source: SignalSource;
  source_id: string;
  username?: string | null;
  content: string;
  locations_mentioned: string[];
  apparent_intent: string;
  intent_score: number;
  intent_level: IntentLevel;
  captured_at: string;
  converted_to_lead: boolean;
  lead_id?: string | null;
};

type SignalListResponse = {
  items: LeadSignal[];
  total: number;
};

type SignalStatsResponse = {
  by_source: Record<string, number>;
  by_intent_level: Record<string, number>;
  by_location: Record<string, number>;
};

async function safeJson<T>(response: Response): Promise<T> {
  const raw = await response.text();
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`Expected JSON from ${response.url}; got status ${response.status}`);
  }
}

export default function SignalsPage() {
  const [signals, setSignals] = useState<LeadSignal[]>([]);
  const [stats, setStats] = useState<SignalStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState<"all" | SignalSource>("all");
  const [intentFilter, setIntentFilter] = useState<"all" | IntentLevel>("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (sourceFilter !== "all") params.set("source", sourceFilter);
      if (intentFilter !== "all") params.set("intent_level", intentFilter);
      const [signalsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/signals?${params.toString()}`),
        fetch(`${API_BASE_URL}/api/signals/stats`),
      ]);
      if (!signalsRes.ok || !statsRes.ok) {
        throw new Error(`Signals fetch failed (signals=${signalsRes.status}, stats=${statsRes.status})`);
      }
      const [signalsJson, statsJson] = await Promise.all([
        safeJson<SignalListResponse>(signalsRes),
        safeJson<SignalStatsResponse>(statsRes),
      ]);
      setSignals(signalsJson.items || []);
      setStats(statsJson);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load signals.");
    } finally {
      setLoading(false);
    }
  }, [sourceFilter, intentFilter]);

  useEffect(() => {
    setLoading(true);
    loadData();
  }, [loadData]);

  async function addToPipeline(signalId: string) {
    await fetch(`${API_BASE_URL}/api/signals/${signalId}/add-to-pipeline`, { method: "POST" });
    await loadData();
  }

  const filtered = useMemo(() => {
    if (!query) return signals;
    const q = query.toLowerCase();
    return signals.filter((s) => {
      return (
        s.content.toLowerCase().includes(q) ||
        (s.username || "").toLowerCase().includes(q) ||
        s.locations_mentioned.join(" ").toLowerCase().includes(q)
      );
    });
  }, [signals, query]);

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-[#1B2A4A]">Lead Signals</h1>
            <p className="mt-1 text-xs text-slate-500">Public intent signals ready for enrichment and routing.</p>
          </div>
          <button onClick={loadData} className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50">
            Refresh
          </button>
        </div>

        {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-500">By Source</p>
            <p className="mt-2 text-sm text-slate-700">
              Reddit RSS: {stats?.by_source?.reddit_rss ?? 0} | Reddit API: {stats?.by_source?.reddit_api ?? 0} | Twitter API: {stats?.by_source?.twitter ?? 0} | Twitter Google: {stats?.by_source?.twitter_google ?? 0} | Alerts:{" "}
              {stats?.by_source?.google_alerts ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-500">Intent Levels</p>
            <p className="mt-2 text-sm text-slate-700">
              Strong: {stats?.by_intent_level?.strong_intent ?? 0} | Moderate: {stats?.by_intent_level?.moderate_intent ?? 0}
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-slate-500">Top Locations</p>
            <p className="mt-2 text-sm text-slate-700">
              {Object.entries(stats?.by_location || {})
                .slice(0, 3)
                .map(([loc, count]) => `${loc} (${count})`)
                .join(", ") || "No location signals yet."}
            </p>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-4">
            <input
              className="rounded border border-slate-300 px-3 py-2 text-sm md:col-span-2"
              placeholder="Search content, username, location"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select className="rounded border border-slate-300 px-2 py-2 text-sm" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as "all" | SignalSource)}>
              <option value="all">All sources</option>
              <option value="reddit_rss">Reddit RSS</option>
              <option value="reddit_api">Reddit API</option>
              <option value="twitter">Twitter API</option>
              <option value="twitter_google">Twitter (Google)</option>
              <option value="google_alerts">Google Alerts</option>
            </select>
            <select className="rounded border border-slate-300 px-2 py-2 text-sm" value={intentFilter} onChange={(e) => setIntentFilter(e.target.value as "all" | IntentLevel)}>
              <option value="all">All intent levels</option>
              <option value="strong_intent">Strong</option>
              <option value="moderate_intent">Moderate</option>
              <option value="weak_intent">Weak</option>
              <option value="not_relevant">Not Relevant</option>
            </select>
          </div>

          <div className="space-y-3">
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded bg-slate-100" />)
            ) : filtered.length === 0 ? (
              <div className="rounded border border-slate-200 p-4 text-sm text-slate-500">No captured signals yet.</div>
            ) : (
              filtered.map((signal) => (
                <article key={signal.id} className="rounded border border-slate-200 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase text-slate-500">
                        {signal.source} • {new Date(signal.captured_at).toLocaleString()}
                      </p>
                      <p className="mt-1 text-sm text-slate-800">{signal.content}</p>
                      <p className="mt-2 text-xs text-slate-500">
                        User: {signal.username || "unknown"} | Intent: {signal.apparent_intent} | Score: {signal.intent_score}/10 | Level:{" "}
                        {signal.intent_level}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Locations: {signal.locations_mentioned.join(", ") || "n/a"}
                      </p>
                    </div>
                    <button
                      onClick={() => addToPipeline(signal.id)}
                      disabled={signal.converted_to_lead}
                      className="rounded bg-[#1B2A4A] px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {signal.converted_to_lead ? "Added" : "Add to Pipeline"}
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

