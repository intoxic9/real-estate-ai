"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import {
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Bar,
  BarChart,
} from "recharts";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

type ScoreBucket = "hot" | "warm" | "cold";
type LeadIntent =
  | "buyer_primary"
  | "buyer_investment"
  | "seller"
  | "renter"
  | "refinance"
  | "buyer"
  | "investor"
  | "unknown";
type FinancingType = "cash" | "conventional" | "fha" | "va" | "other" | "unknown";

type LeadProfile = {
  id: string;
  full_name?: string | null;
  email?: string | null;
  intent?: LeadIntent;
  target_market?: string | null;
  preferred_locations?: string[];
  financing_type?: FinancingType;
  is_first_time_buyer?: boolean | null;
  timeline?: string | null;
  created_at: string;
};

type ScoreResult = {
  heat_score: number;
  bucket: ScoreBucket;
  signals?: string[];
  timestamp: string;
};

type ComplianceResult = {
  compliant: boolean;
  consent_verified: boolean;
  blocked_claims: string[];
  sanitized_transcript: string;
};

type LeadListItem = {
  lead: LeadProfile;
  latest_score?: ScoreResult | null;
  latest_compliance?: ComplianceResult | null;
};

type LeadsResponse = {
  items: LeadListItem[];
  total: number;
};

type LeadDetailResponse = {
  lead: LeadProfile;
  scores: ScoreResult[];
  compliance_results: ComplianceResult[];
  transcript: Array<{
    role: "user" | "assistant" | "system";
    content: string;
    timestamp: string;
    metadata?: Record<string, unknown> | null;
  }>;
};

type AnalyticsOverview = {
  total_leads: number;
  hot_leads: number;
  warm_leads: number;
  cold_leads: number;
  conversion_rate: number;
  average_score: number;
};

type TrendPoint = { timestamp: string; lead_volume: number };
type HotLeadNotification = {
  id: string;
  lead_id: string;
  lead_name?: string | null;
  intent: LeadIntent;
  score: number;
  budget_summary: string;
  market: string;
  timeline: string;
  destination: string;
  lead_url?: string | null;
  unread: boolean;
  created_at: string;
};
type NotificationsResponse = {
  items: HotLeadNotification[];
  unread_count: number;
};

const US_MARKETS = [
  "All Markets",
  "New York Metro",
  "Austin TX",
  "Miami FL",
  "Dallas-Fort Worth TX",
  "Phoenix AZ",
  "Seattle WA",
  "Atlanta GA",
];
const FINANCING_FILTERS: Array<"all" | FinancingType> = [
  "all",
  "fha",
  "va",
  "conventional",
  "cash",
  "other",
  "unknown",
];

function pill(bucket?: ScoreBucket) {
  if (bucket === "hot") return "border border-rose-200 bg-rose-50 text-rose-700";
  if (bucket === "warm") return "border border-amber-200 bg-amber-50 text-amber-700";
  return "border border-slate-200 bg-slate-50 text-slate-600";
}

function scorePill(score: number) {
  if (score >= 70) return "bg-emerald-100 text-emerald-700";
  if (score >= 40) return "bg-amber-100 text-amber-700";
  return "bg-slate-200 text-slate-600";
}

export default function DashboardPage() {
  const [leadsData, setLeadsData] = useState<LeadsResponse | null>(null);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [trends, setTrends] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, LeadDetailResponse>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [bucketFilter, setBucketFilter] = useState<"all" | ScoreBucket>("all");
  const [intentFilter, setIntentFilter] = useState<"all" | LeadIntent>("all");
  const [marketFilter, setMarketFilter] = useState("All Markets");
  const [financingFilter, setFinancingFilter] = useState<"all" | FinancingType>("all");
  const [firstTimeOnly, setFirstTimeOnly] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sortBy, setSortBy] = useState<"score" | "date" | "bucket">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<HotLeadNotification[]>([]);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);

  async function safeJson<T>(response: Response): Promise<T> {
    const raw = await response.text();
    try {
      return JSON.parse(raw) as T;
    } catch {
      const preview = raw.slice(0, 120).replace(/\s+/g, " ");
      throw new Error(
        `Expected JSON from ${response.url}, got non-JSON payload (status ${response.status}): ${preview}`
      );
    }
  }

  const loadDashboard = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    setRefreshing(true);
    setLoadError(null);
    try {
      const [leadsRes, overviewRes, trendsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/leads`),
        fetch(`${API_BASE_URL}/api/analytics/overview`),
        fetch(`${API_BASE_URL}/api/analytics/trends`),
      ]);
      if (!leadsRes.ok || !overviewRes.ok || !trendsRes.ok) {
        throw new Error(
          `Dashboard fetch failed (leads=${leadsRes.status}, overview=${overviewRes.status}, trends=${trendsRes.status})`
        );
      }
      const [leadsJson, overviewJson, trendsJson] = await Promise.all([
        safeJson<LeadsResponse>(leadsRes),
        safeJson<AnalyticsOverview>(overviewRes),
        safeJson<TrendPoint[]>(trendsRes),
      ]);
      setLeadsData(leadsJson);
      setOverview(overviewJson);
      setTrends(Array.isArray(trendsJson) ? trendsJson : []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load dashboard data.";
      setLoadError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadNotifications = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/notifications/hot-leads?limit=8`);
      if (!res.ok) return;
      const json = await safeJson<NotificationsResponse>(res);
      setNotifications(Array.isArray(json.items) ? json.items : []);
      setUnreadNotifications(Number(json.unread_count || 0));
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    loadDashboard(true);
    const timer = setInterval(() => loadDashboard(false), 30000);
    return () => clearInterval(timer);
  }, [loadDashboard]);

  useEffect(() => {
    loadNotifications();
    const timer = setInterval(() => loadNotifications(), 30000);
    return () => clearInterval(timer);
  }, [loadNotifications]);

  const filteredRows = useMemo(() => {
    const rows = (leadsData?.items ?? []).filter((item) => {
      const lead = item.lead;
      const score = item.latest_score;
      const haystack = `${lead.full_name ?? ""} ${lead.email ?? ""}`.toLowerCase();
      if (search && !haystack.includes(search.toLowerCase())) return false;
      if (bucketFilter !== "all" && score?.bucket !== bucketFilter) return false;
      if (intentFilter !== "all" && lead.intent !== intentFilter) return false;
      if (marketFilter !== "All Markets" && lead.target_market !== marketFilter) return false;
      if (financingFilter !== "all" && lead.financing_type !== financingFilter) return false;
      if (firstTimeOnly && !lead.is_first_time_buyer) return false;
      if (fromDate && new Date(lead.created_at) < new Date(fromDate)) return false;
      if (toDate && new Date(lead.created_at) > new Date(`${toDate}T23:59:59`)) return false;
      return true;
    });

    const bucketRank: Record<ScoreBucket, number> = { hot: 3, warm: 2, cold: 1 };
    rows.sort((a, b) => {
      if (sortBy === "score") {
        const av = a.latest_score?.heat_score ?? 0;
        const bv = b.latest_score?.heat_score ?? 0;
        return sortDir === "asc" ? av - bv : bv - av;
      }
      if (sortBy === "bucket") {
        const av = bucketRank[a.latest_score?.bucket ?? "cold"];
        const bv = bucketRank[b.latest_score?.bucket ?? "cold"];
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const av = new Date(a.lead.created_at).getTime();
      const bv = new Date(b.lead.created_at).getTime();
      return sortDir === "asc" ? av - bv : bv - av;
    });
    return rows;
  }, [
    leadsData?.items,
    search,
    bucketFilter,
    intentFilter,
    marketFilter,
    financingFilter,
    firstTimeOnly,
    fromDate,
    toDate,
    sortBy,
    sortDir,
  ]);

  const intentDistribution = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of filteredRows) {
      const key = item.lead.intent ?? "unknown";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return Array.from(counts.entries()).map(([name, value]) => ({ name, value }));
  }, [filteredRows]);

  const scoreBins = useMemo(() => {
    const bins = [
      { range: "0-20", count: 0 },
      { range: "21-40", count: 0 },
      { range: "41-60", count: 0 },
      { range: "61-80", count: 0 },
      { range: "81-100", count: 0 },
    ];
    for (const item of filteredRows) {
      const score = item.latest_score?.heat_score ?? 0;
      if (score <= 20) bins[0].count += 1;
      else if (score <= 40) bins[1].count += 1;
      else if (score <= 60) bins[2].count += 1;
      else if (score <= 80) bins[3].count += 1;
      else bins[4].count += 1;
    }
    return bins;
  }, [filteredRows]);

  async function toggleExpand(leadId: string) {
    const next = expandedId === leadId ? null : leadId;
    setExpandedId(next);
    if (!next || details[leadId]) return;
    setDetailLoadingId(leadId);
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/${leadId}`);
      if (!res.ok) {
        throw new Error(`Lead detail request failed (${res.status}).`);
      }
      const json = await safeJson<LeadDetailResponse>(res);
      setDetails((prev) => ({ ...prev, [leadId]: json }));
    } finally {
      setDetailLoadingId(null);
    }
  }

  async function routeLead(leadId: string) {
    await fetch(`${API_BASE_URL}/api/leads/${leadId}/route`, { method: "POST" });
    await loadDashboard(false);
  }

  async function deleteLead(leadId: string) {
    const confirmed = window.confirm(
      "PDPL confirmation: this will permanently delete lead data. Continue?"
    );
    if (!confirmed) return;
    await fetch(`${API_BASE_URL}/api/leads/${leadId}`, { method: "DELETE" });
    setExpandedId(null);
    await loadDashboard(false);
  }

  async function editLead(lead: LeadProfile) {
    const updatedName = window.prompt("Edit lead name", lead.full_name ?? "") ?? lead.full_name ?? null;
    await fetch(`${API_BASE_URL}/api/leads/${lead.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: updatedName }),
    });
    await loadDashboard(false);
  }

  async function openNotification(n: HotLeadNotification) {
    setShowNotifications(false);
    if (n.unread) {
      await fetch(`${API_BASE_URL}/api/notifications/hot-leads/${n.id}/read`, { method: "POST" });
      await loadNotifications();
    }
  }

  const total = overview?.total_leads ?? 0;
  const routed = Math.round((overview?.conversion_rate ?? 0) * total);

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-[1400px] space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-[#1B2A4A]">Lead Dashboard</h1>
            <p className="mt-1 text-xs text-slate-500">Monitor intake, compliance, and routing outcomes.</p>
          </div>
          <div className="relative flex items-center gap-2">
            <button
              type="button"
              className="relative rounded-lg border border-slate-300 bg-white p-2 hover:bg-slate-50"
              onClick={() => setShowNotifications((v) => !v)}
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5 text-slate-700" />
              {unreadNotifications > 0 && (
                <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
                  {unreadNotifications > 99 ? "99+" : unreadNotifications}
                </span>
              )}
            </button>
            {showNotifications && (
              <div className="absolute right-0 top-12 z-20 w-[360px] rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
                <div className="border-b border-slate-200 px-2 pb-2 text-sm font-semibold text-[#1B2A4A]">
                  Hot Lead Notifications
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {notifications.length === 0 ? (
                    <p className="px-2 py-4 text-sm text-slate-500">No hot lead notifications yet.</p>
                  ) : (
                    notifications.map((n) => (
                      <Link
                        key={n.id}
                        href={n.lead_url || `/dashboard?leadId=${n.lead_id}`}
                        onClick={() => openNotification(n)}
                        className={`block rounded-lg px-2 py-2 text-sm hover:bg-slate-50 ${n.unread ? "bg-rose-50/40" : ""}`}
                      >
                        <p className="font-medium text-slate-900">
                          🔥 Score {n.score} - {n.intent}
                        </p>
                        <p className="mt-0.5 text-xs text-slate-600">
                          Budget: {n.budget_summary} | Market: {n.market} | Timeline: {n.timeline}
                        </p>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          {new Date(n.created_at).toLocaleString()}
                        </p>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            )}
            <Button onClick={() => loadDashboard(false)} variant="outline" size="md">
              {refreshing ? "Refreshing..." : "Refresh"}
            </Button>
          </div>
        </div>
        {loadError && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {loadError}
          </div>
        )}

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-6">
          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
              ))
            : [
                { label: "Total Leads", value: total, sub: "↗ +4.2% vs last week", accent: "border-[#2E75B6]" },
                { label: "Hot Leads", value: overview?.hot_leads ?? 0, accent: "border-rose-500" },
                { label: "Warm Leads", value: overview?.warm_leads ?? 0, accent: "border-amber-500" },
                { label: "Cold Leads", value: overview?.cold_leads ?? 0, accent: "border-slate-400" },
                { label: "Avg Heat Score", value: `${overview?.average_score ?? 0}`, accent: "border-[#2E75B6]" },
                { label: "Conversion Rate", value: `${Math.round((overview?.conversion_rate ?? 0) * 100)}%`, sub: `${routed}/${total} routed`, accent: "border-[#2E75B6]" },
              ].map((card) => (
                <div
                  key={card.label}
                  className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm border-l-4 ${card.accent}`}
                >
                  <p className="text-xs uppercase tracking-wide text-slate-500">{card.label}</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">{card.value}</p>
                  {card.sub && <p className="mt-1 text-xs text-slate-600">{card.sub}</p>}
                </div>
              ))}
        </section>

        <Card className="rounded-xl border border-slate-200 bg-white p-0">
          <CardHeader className="p-4">
            <CardTitle className="text-sm font-semibold text-slate-800">Filters</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
          <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-8">
            <input
              className="rounded border border-slate-300 px-3 py-2 text-sm xl:col-span-2"
              placeholder="Search name or email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select className="rounded border border-slate-300 px-2 py-2 text-sm" value={marketFilter} onChange={(e) => setMarketFilter(e.target.value)}>
              {US_MARKETS.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
            <select className="rounded border border-slate-300 px-2 py-2 text-sm" value={financingFilter} onChange={(e) => setFinancingFilter(e.target.value as "all" | FinancingType)}>
              {FINANCING_FILTERS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
            <select className="rounded border border-slate-300 px-2 py-2 text-sm" value={bucketFilter} onChange={(e) => setBucketFilter(e.target.value as "all" | ScoreBucket)}>
              <option value="all">all buckets</option>
              <option value="hot">hot</option>
              <option value="warm">warm</option>
              <option value="cold">cold</option>
            </select>
            <input type="date" className="rounded border border-slate-300 px-2 py-2 text-sm" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            <input type="date" className="rounded border border-slate-300 px-2 py-2 text-sm" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            <label className="inline-flex items-center gap-2 rounded border border-slate-300 px-2 py-2 text-sm">
              <input type="checkbox" checked={firstTimeOnly} onChange={(e) => setFirstTimeOnly(e.target.checked)} />
              First-Time Buyer
            </label>
          </div>

          <div className="mb-3 flex gap-2 text-sm">
            {(["score", "date", "bucket"] as const).map((key) => (
              <button
                key={key}
                onClick={() => {
                  if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                  else setSortBy(key);
                }}
                className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-50"
              >
                Sort {key} {sortBy === key ? (sortDir === "asc" ? "↑" : "↓") : ""}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[1200px] w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">Name</th>
                  <th>Intent</th>
                  <th>Score</th>
                  <th>Bucket</th>
                  <th>Target Market(s)</th>
                  <th>Financing</th>
                  <th>Pre-Approval</th>
                  <th>Timeline</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-3" colSpan={11}>
                        <div className="h-8 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))
                ) : filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="py-6 text-center text-slate-500">
                      No leads match current filters.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((item, idx) => {
                    const lead = item.lead;
                    const score = item.latest_score?.heat_score ?? 0;
                    const bucket = item.latest_score?.bucket;
                    const detail = details[lead.id];
                    const zebra = idx % 2 === 0 ? "bg-white" : "bg-slate-50";
                    return (
                      <Fragment key={lead.id}>
                        <tr
                          className={`cursor-pointer border-b border-slate-100 ${zebra} hover:bg-slate-100`}
                          onClick={() => toggleExpand(lead.id)}
                        >
                          <td className="py-3">{lead.full_name ?? lead.email ?? "Unknown"}</td>
                          <td>{lead.intent ?? "unknown"}</td>
                          <td className="py-3">
                            <span
                              className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${scorePill(score)}`}
                            >
                              {score}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${pill(
                                bucket
                              )}`}
                            >
                              {bucket ?? "cold"}
                            </span>
                          </td>
                          <td>{lead.target_market ?? lead.preferred_locations?.join(", ") ?? "-"}</td>
                          <td>{lead.financing_type ?? "unknown"}</td>
                          <td>
                            {item.latest_score?.signals?.join(" ").toLowerCase().includes("pre-approv")
                              ? "Yes"
                              : "Unknown"}
                          </td>
                          <td>{lead.timeline ?? "-"}</td>
                          <td>{new Date(lead.created_at).toLocaleDateString()}</td>
                          <td>{item.latest_compliance?.compliant ? "Compliant" : "Review"}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <div className="flex gap-1">
                              <button className="rounded border px-2 py-1 text-xs" onClick={() => routeLead(lead.id)}>
                                Route
                              </button>
                              <button className="rounded border px-2 py-1 text-xs" onClick={() => editLead(lead)}>
                                Edit
                              </button>
                              <button className="rounded border border-rose-300 px-2 py-1 text-xs text-rose-700" onClick={() => deleteLead(lead.id)}>
                                Delete
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedId === lead.id && (
                          <tr className="bg-slate-50/70">
                            <td colSpan={11} className="p-3">
                              {detailLoadingId === lead.id ? (
                                <div className="h-16 animate-pulse rounded bg-slate-100" />
                              ) : detail ? (
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                                  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                                    <p className="text-xs font-semibold uppercase text-slate-500">
                                      Agent Results
                                    </p>
                                    <p className="mt-2 text-xs text-slate-700">
                                      Scores: {detail.scores.map((s) => s.heat_score).join(", ")}
                                    </p>
                                  </div>
                                  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                                    <p className="text-xs font-semibold uppercase text-slate-500">
                                      Compliance Status
                                    </p>
                                    <p className="mt-2 text-xs text-slate-700">
                                      {detail.compliance_results[0]?.compliant
                                        ? "Compliant"
                                        : "Needs review"}
                                    </p>
                                    <p className="mt-1 text-xs text-slate-500">
                                      Consent:{" "}
                                      {detail.compliance_results[0]?.consent_verified
                                        ? "verified"
                                        : "not verified"}
                                    </p>
                                  </div>
                                  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                                    <p className="text-xs font-semibold uppercase text-slate-500">
                                      Transcript
                                    </p>
                                    {detail.transcript?.length ? (
                                      <div className="mt-2 max-h-72 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2">
                                        {detail.transcript.map((entry, idx) => {
                                          const isUser = entry.role === "user";
                                          return (
                                            <div
                                              key={`${entry.timestamp}-${idx}`}
                                              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                                            >
                                              <div
                                                className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-2 py-1 text-xs leading-snug ${
                                                  isUser
                                                    ? "bg-[#1B2A4A] text-white"
                                                    : "bg-[#F2F2F2] text-slate-900"
                                                }`}
                                              >
                                                <div className="font-semibold uppercase tracking-wide text-[10px] opacity-70 mb-1">
                                                  {isUser ? "You" : "Assistant"}
                                                </div>
                                                <div>{entry.content}</div>
                                                <div
                                                  className={`mt-1 text-[10px] ${
                                                    isUser ? "text-white/70" : "text-slate-400"
                                                  } ${isUser ? "text-right" : "text-left"}`}
                                                >
                                                  {new Date(entry.timestamp).toLocaleString()}
                                                </div>
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    ) : (
                                      <p className="mt-2 text-xs text-slate-600">
                                        Transcript not available from current endpoint.
                                      </p>
                                    )}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-xs text-slate-500">No detail available.</p>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          </CardContent>
        </Card>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-slate-800">Leads Over Time (30 days)</p>
            {loading ? (
              <div className="h-64 animate-pulse rounded bg-slate-100" />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trends}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleDateString()} />
                    <YAxis />
                    <Tooltip labelFormatter={(v) => new Date(String(v)).toLocaleString()} />
                    <Line type="monotone" dataKey="lead_volume" stroke="#2E75B6" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-slate-800">Intent Distribution</p>
            {loading ? (
              <div className="h-64 animate-pulse rounded bg-slate-100" />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={intentDistribution} dataKey="value" nameKey="name" outerRadius={90} innerRadius={50}>
                      {intentDistribution.map((_, i) => (
                        <Cell key={i} fill={["#1B2A4A", "#2E75B6", "#0EA5E9", "#F59E0B", "#EF4444", "#64748B"][i % 6]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-slate-800">Score Distribution</p>
            {loading ? (
              <div className="h-64 animate-pulse rounded bg-slate-100" />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={scoreBins}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="range" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#1B2A4A" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

