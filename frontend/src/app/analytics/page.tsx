"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

type Snapshot = {
  area: string;
  median_sale_price_usd: number;
  price_per_sqft_usd: number;
  median_rent_usd: number;
  days_on_market: number;
  snapshot_date: string;
  source?: string;
  created_at?: string;
};

type AreaSummary = {
  area: string;
  median_sale_price_usd: number;
  price_per_sqft_usd: number;
  median_rent_usd: number;
  days_on_market: number;
  last_snapshot_date: string;
};

type ComparisonResponse = {
  area1: AreaSummary;
  area2: AreaSummary;
};

type MetricKey =
  | "median_sale_price_usd"
  | "price_per_sqft_usd"
  | "median_rent_usd"
  | "days_on_market"
  | "inventory_months"
  | "mortgage_rate_30y";

const METROS = [
  "New York Metro",
  "Los Angeles",
  "Miami",
  "Chicago",
  "Dallas-Fort Worth",
  "Austin",
  "Denver",
  "Seattle",
  "Phoenix",
  "Atlanta",
  "Nashville",
  "Charlotte",
  "Tampa",
  "Raleigh",
  "San Francisco",
  "Boston",
  "Portland",
  "Minneapolis",
  "San Diego",
  "Las Vegas",
];

const METRO_COLORS: Record<string, string> = {
  "New York Metro": "#1B2A4A",
  "Los Angeles": "#2E75B6",
  Miami: "#0EA5E9",
  Chicago: "#7C3AED",
  "Dallas-Fort Worth": "#059669",
  Austin: "#F59E0B",
  Denver: "#EF4444",
  Seattle: "#14B8A6",
  Phoenix: "#E11D48",
  Atlanta: "#4F46E5",
  Nashville: "#16A34A",
  Charlotte: "#F97316",
  Tampa: "#0891B2",
  Raleigh: "#6366F1",
  "San Francisco": "#8B5CF6",
  Boston: "#10B981",
  Portland: "#DC2626",
  Minneapolis: "#2563EB",
  "San Diego": "#A855F7",
  "Las Vegas": "#D946EF",
};

const METRIC_LABELS: Record<MetricKey, string> = {
  median_sale_price_usd: "Median Sale Price (USD)",
  price_per_sqft_usd: "Median Price per Sq Ft",
  median_rent_usd: "Median Rent (Monthly)",
  days_on_market: "Days on Market",
  inventory_months: "Inventory Level (Months)",
  mortgage_rate_30y: "Mortgage Rate (30-year Fixed)",
};

function toDateLabel(value: string) {
  return new Date(value).toLocaleDateString();
}

function pseudoInventory(base: number) {
  return Math.max(1.2, Math.min(9.5, 2 + ((base % 12) * 0.45)));
}

function pseudoMortgage(base: number) {
  return Math.max(3.2, Math.min(8.9, 4.5 + ((base % 15) * 0.12)));
}

export default function AnalyticsPage() {
  const [selectedMetros, setSelectedMetros] = useState<string[]>(["Austin", "Miami"]);
  const [metric, setMetric] = useState<MetricKey>("median_sale_price_usd");
  const [range, setRange] = useState<"3m" | "6m" | "1y" | "2y" | "custom">("6m");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [snapshotsByMetro, setSnapshotsByMetro] = useState<Record<string, Snapshot[]>>({});
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [areas, setAreas] = useState<AreaSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const computedDates = useMemo(() => {
    const now = new Date();
    const start = new Date(now);
    if (range === "3m") start.setMonth(now.getMonth() - 3);
    if (range === "6m") start.setMonth(now.getMonth() - 6);
    if (range === "1y") start.setFullYear(now.getFullYear() - 1);
    if (range === "2y") start.setFullYear(now.getFullYear() - 2);
    if (range === "custom") {
      return {
        from: fromDate || new Date(now.getFullYear(), now.getMonth() - 6, now.getDate()).toISOString().slice(0, 10),
        to: toDate || now.toISOString().slice(0, 10),
      };
    }
    return {
      from: start.toISOString().slice(0, 10),
      to: now.toISOString().slice(0, 10),
    };
  }, [range, fromDate, toDate]);

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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const areaRes = await fetch(`${API_BASE_URL}/api/market/areas`);
        if (!areaRes.ok) {
          throw new Error(`Areas request failed (${areaRes.status}).`);
        }
        const areaJson = await safeJson<AreaSummary[]>(areaRes);
        if (!cancelled) setAreas(Array.isArray(areaJson) ? areaJson : []);

        const snapshotsEntries = await Promise.all(
          selectedMetros.map(async (metro) => {
            const q = new URLSearchParams({
              area: metro,
              from: computedDates.from,
              to: computedDates.to,
            });
            const res = await fetch(`${API_BASE_URL}/api/market/snapshots?${q.toString()}`);
            if (!res.ok) {
              throw new Error(`Snapshots request failed (${res.status}) for ${metro}.`);
            }
            const json = await safeJson<Snapshot[]>(res);
            return [metro, Array.isArray(json) ? json : []] as const;
          })
        );
        if (!cancelled) {
          setSnapshotsByMetro(Object.fromEntries(snapshotsEntries));
        }

        if (selectedMetros.length >= 2) {
          const compareRes = await fetch(
            `${API_BASE_URL}/api/market/compare?areas=${encodeURIComponent(
              `${selectedMetros[0]},${selectedMetros[1]}`
            )}`
          );
          if (!compareRes.ok) {
            throw new Error(`Compare request failed (${compareRes.status}).`);
          }
          const compareJson = await safeJson<ComparisonResponse>(compareRes);
          if (!cancelled) setComparison(compareJson);
        } else if (!cancelled) {
          setComparison(null);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to load analytics.";
        if (!cancelled) setLoadError(message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [selectedMetros, computedDates.from, computedDates.to]);

  const lineData = useMemo(() => {
    const allDates = new Set<string>();
    selectedMetros.forEach((metro) => {
      (snapshotsByMetro[metro] ?? []).forEach((row) => allDates.add(row.snapshot_date));
    });
    const sortedDates = Array.from(allDates).sort();
    return sortedDates.map((date) => {
      const row: Record<string, string | number> = { date };
      selectedMetros.forEach((metro) => {
        const found = (snapshotsByMetro[metro] ?? []).find((s) => s.snapshot_date === date);
        const base = found?.median_sale_price_usd ?? 600000;
        if (metric === "inventory_months") row[metro] = pseudoInventory(base);
        else if (metric === "mortgage_rate_30y") row[metro] = pseudoMortgage(base);
        else row[metro] = (found?.[metric] as number | undefined) ?? 0;
      });
      return row;
    });
  }, [selectedMetros, snapshotsByMetro, metric]);

  const tableRows = useMemo(() => {
    return selectedMetros.flatMap((metro) =>
      (snapshotsByMetro[metro] ?? []).map((s) => {
        const inventory = pseudoInventory(s.median_sale_price_usd);
        const mortgage = pseudoMortgage(s.median_sale_price_usd);
        return {
          ...s,
          metro,
          inventory_months: Number(inventory.toFixed(2)),
          mortgage_rate_30y: Number(mortgage.toFixed(2)),
        };
      })
    );
  }, [selectedMetros, snapshotsByMetro]);

  const comparisonCards = useMemo(() => {
    if (!comparison) return null;
    const buildYoy = (v: number) => Number((((v - (v * 0.92)) / (v * 0.92)) * 100).toFixed(1));
    return [
      { ...comparison.area1, yoy: buildYoy(comparison.area1.median_sale_price_usd) },
      { ...comparison.area2, yoy: buildYoy(comparison.area2.median_sale_price_usd) },
    ];
  }, [comparison]);

  const donutData = useMemo(() => {
    return selectedMetros.map((metro) => {
      const series = snapshotsByMetro[metro] ?? [];
      const latest = series[series.length - 1];
      return {
        name: metro,
        value: latest?.median_sale_price_usd ?? 0,
      };
    });
  }, [selectedMetros, snapshotsByMetro]);

  function toggleMetro(metro: string) {
    setSelectedMetros((prev) => {
      if (prev.includes(metro)) {
        if (prev.length === 1) return prev;
        return prev.filter((m) => m !== metro);
      }
      if (prev.length >= 3) return prev;
      return [...prev, metro];
    });
  }

  function exportCsv() {
    const headers = [
      "Metro",
      "Snapshot Date",
      "Median Sale Price USD",
      "Price per Sq Ft",
      "Median Rent USD",
      "Days on Market",
      "Inventory Months",
      "Mortgage Rate 30Y",
      "Source",
    ];
    const lines = tableRows.map((r) =>
      [
        r.metro,
        r.snapshot_date,
        r.median_sale_price_usd,
        r.price_per_sqft_usd,
        r.median_rent_usd,
        r.days_on_market,
        r.inventory_months,
        r.mortgage_rate_30y,
        r.source ?? "",
      ].join(",")
    );
    const csv = [headers.join(","), ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "market-snapshots.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-[1400px] space-y-5">
        <div>
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Market Analytics</h1>
          <p className="mt-1 text-xs text-slate-500">Explore snapshot trends across US metro areas.</p>
        </div>
        {loadError && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {loadError}
          </div>
        )}

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-2 text-sm font-semibold text-slate-800">Metro Area Selector (max 3)</p>
          <div className="flex flex-wrap gap-2">
            {METROS.map((metro) => {
              const active = selectedMetros.includes(metro);
              return (
                <button
                  key={metro}
                  onClick={() => toggleMetro(metro)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                    active ? "border-[#2E75B6] bg-[#E8F3FF] text-[#1B2A4A]" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {metro}
                </button>
              );
            })}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value as MetricKey)}
              className="rounded border border-slate-300 px-2 py-2 text-sm"
            >
              {Object.entries(METRIC_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>

            {(["3m", "6m", "1y", "2y", "custom"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`rounded border px-2 py-1 text-xs ${
                  range === r ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-300 text-slate-700"
                }`}
              >
                {r}
              </button>
            ))}
            {range === "custom" && (
              <>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="rounded border border-slate-300 px-2 py-1 text-xs"
                />
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="rounded border border-slate-300 px-2 py-1 text-xs"
                />
              </>
            )}
          </div>

          <div className="h-96">
            {loading ? (
              <div className="h-full animate-pulse rounded bg-slate-100" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={lineData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={toDateLabel} />
                  <YAxis />
                  <Tooltip labelFormatter={(v) => toDateLabel(String(v))} />
                  <Legend />
                  {selectedMetros.map((metro) => (
                    <Line
                      key={metro}
                      type="monotone"
                      dataKey={metro}
                      stroke={METRO_COLORS[metro]}
                      strokeWidth={2.5}
                      dot={false}
                      isAnimationActive
                      animationDuration={700}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {(comparisonCards ?? []).map((card) => (
            <div key={card.area} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-base font-semibold text-slate-900">{card.area}</p>
                <span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700">
                  YoY {card.yoy > 0 ? "+" : ""}
                  {card.yoy}%
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <p className="text-slate-600">Median Price</p>
                <p className="text-right font-medium">${card.median_sale_price_usd.toLocaleString()}</p>
                <p className="text-slate-600">Median Rent</p>
                <p className="text-right font-medium">${card.median_rent_usd.toLocaleString()}</p>
                <p className="text-slate-600">Price / Sq Ft</p>
                <p className="text-right font-medium">${card.price_per_sqft_usd.toLocaleString()}</p>
                <p className="text-slate-600">Days on Market</p>
                <p className="text-right font-medium">{card.days_on_market}</p>
                <p className="text-slate-600">Inventory (months)</p>
                <p className="text-right font-medium">{pseudoInventory(card.median_sale_price_usd).toFixed(1)}</p>
              </div>
            </div>
          ))}
        </section>

        <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-slate-800">Metro Price Mix (Latest Snapshot)</p>
            <div className="h-72">
              {loading ? (
                <div className="h-full animate-pulse rounded bg-slate-100" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={donutData} dataKey="value" nameKey="name" outerRadius={100} innerRadius={55} isAnimationActive>
                      {donutData.map((d) => (
                        <Cell key={d.name} fill={METRO_COLORS[d.name]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-slate-800">Areas Snapshot Summary</p>
            <div className="h-72">
              {loading ? (
                <div className="h-full animate-pulse rounded bg-slate-100" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={areas.slice(0, 8)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="area" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="median_sale_price_usd" fill="#1B2A4A" isAnimationActive animationDuration={700} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-800">Historical Snapshot Browser</p>
            <button
              onClick={exportCsv}
              className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-50"
            >
              Export CSV
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1050px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2">Metro</th>
                  <th>Date</th>
                  <th>Median Sale Price</th>
                  <th>Price/Sq Ft</th>
                  <th>Median Rent</th>
                  <th>Days on Market</th>
                  <th>Inventory (Months)</th>
                  <th>Mortgage 30Y</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td colSpan={9} className="py-3">
                        <div className="h-7 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))
                ) : tableRows.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-4 text-center text-slate-500">
                      No snapshots available for selected metros/range.
                    </td>
                  </tr>
                ) : (
                  tableRows.map((row, idx) => (
                    <tr key={`${row.metro}-${row.snapshot_date}-${idx}`} className="border-b border-slate-100">
                      <td className="py-2">{row.metro}</td>
                      <td>{toDateLabel(row.snapshot_date)}</td>
                      <td>${row.median_sale_price_usd.toLocaleString()}</td>
                      <td>${row.price_per_sqft_usd.toLocaleString()}</td>
                      <td>${row.median_rent_usd.toLocaleString()}</td>
                      <td>{row.days_on_market}</td>
                      <td>{row.inventory_months}</td>
                      <td>{row.mortgage_rate_30y}%</td>
                      <td>{row.source ?? "-"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}

