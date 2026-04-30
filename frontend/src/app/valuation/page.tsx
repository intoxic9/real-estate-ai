"use client";

import { FormEvent, useMemo, useState } from "react";
import { ArrowRight, Home, Sparkles } from "lucide-react";

type Condition = "excellent" | "good" | "fair" | "needs_work";
type Renovation = "recent_full" | "partial" | "none";
type Trend = "up" | "down" | "flat";

type EstimateResponse = {
  address: string;
  area: string;
  estimated_low: number;
  estimated_mid: number;
  estimated_high: number;
  area_avg_price_per_sqft: number;
  adjusted_price_per_sqft: number;
  market_trend: Trend;
  trend_percent: number;
  generated_at: string;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const questions = [
  "When was it last renovated?",
  "How many bedrooms and bathrooms?",
  "Any major upgrades (kitchen, roof, HVAC)?",
  "What condition would you rate it: excellent, good, fair, needs work?",
];

function money(value: number) {
  return `$${Math.round(value).toLocaleString()}`;
}

export default function ValuationPage() {
  const [address, setAddress] = useState("");
  const [area, setArea] = useState("");
  const [sqft, setSqft] = useState("");
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<string[]>([]);
  const [currentAnswer, setCurrentAnswer] = useState("");

  const [bedrooms, setBedrooms] = useState(3);
  const [bathrooms, setBathrooms] = useState(2);
  const [condition, setCondition] = useState<Condition>("good");
  const [renovation, setRenovation] = useState<Renovation>("none");
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showCtaForm, setShowCtaForm] = useState(false);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [ctaStatus, setCtaStatus] = useState<string | null>(null);

  const trendLabel = useMemo(() => {
    if (!estimate) return "";
    if (estimate.market_trend === "up") return `Up ${estimate.trend_percent}%`;
    if (estimate.market_trend === "down") return `Down ${Math.abs(estimate.trend_percent)}%`;
    return "Flat";
  }, [estimate]);

  function startFlow(e: FormEvent) {
    e.preventDefault();
    if (!address.trim() || !area.trim() || !sqft.trim()) return;
    setStep(1);
    setAnswers([]);
    setCurrentAnswer("");
    setEstimate(null);
    setError(null);
  }

  function nextQuestion(e: FormEvent) {
    e.preventDefault();
    if (!currentAnswer.trim()) return;
    const nextAnswers = [...answers, currentAnswer.trim()];
    setAnswers(nextAnswers);
    setCurrentAnswer("");

    if (step === 2) {
      const m = nextAnswers[1].match(/(\d+)\D+(\d+(\.\d+)?)/);
      if (m) {
        setBedrooms(Number(m[1]));
        setBathrooms(Number(m[2]));
      }
    }

    if (step === 1) {
      const lower = nextAnswers[0].toLowerCase();
      if (lower.includes("full") || lower.includes("202") || lower.includes("recent")) {
        setRenovation("recent_full");
      } else if (lower.includes("partial") || lower.includes("some")) {
        setRenovation("partial");
      } else {
        setRenovation("none");
      }
    }

    if (step === 4) {
      const lower = nextAnswers[3].toLowerCase();
      if (lower.includes("excellent")) setCondition("excellent");
      else if (lower.includes("fair")) setCondition("fair");
      else if (lower.includes("needs")) setCondition("needs_work");
      else setCondition("good");
      void runEstimate();
      return;
    }
    setStep((s) => s + 1);
  }

  async function runEstimate() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/valuation/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address,
          area,
          sqft: Number(sqft),
          bedrooms,
          bathrooms,
          condition,
          renovations: renovation,
        }),
      });
      if (!res.ok) throw new Error(`Valuation failed (${res.status})`);
      const data = (await res.json()) as EstimateResponse;
      setEstimate(data);
      setStep(5);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate estimate.");
    } finally {
      setLoading(false);
    }
  }

  async function submitCtaLead(e: FormEvent) {
    e.preventDefault();
    if (!estimate) return;
    setCtaStatus("Submitting...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/import/clay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          email,
          phone,
          intent: "seller",
          target_market: area,
          timeline: "1_3_months",
          property_type: "single_family",
          budget_min: estimate.estimated_low,
          budget_max: estimate.estimated_high,
          financing_type: "other",
          consent_given: true,
          source: "valuation_tool",
        }),
      });
      if (!res.ok) throw new Error(`Lead capture failed (${res.status})`);
      setCtaStatus("Thanks! An agent will reach out with a detailed CMA.");
    } catch (err) {
      setCtaStatus(err instanceof Error ? err.message : "Unable to capture lead.");
    }
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-[#1B2A4A]">
            <Home className="h-5 w-5" />
            <h1 className="text-2xl font-semibold">Free AI Home Valuation</h1>
          </div>
          <p className="mt-2 text-sm text-slate-600">
            Get an instant estimate using local market comps and property adjustments.
          </p>

          {step === 0 && (
            <form onSubmit={startFlow} className="mt-5 space-y-3">
              <input
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Property address"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                required
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <input
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  placeholder="Area / Metro (e.g. Austin)"
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  required
                />
                <input
                  value={sqft}
                  onChange={(e) => setSqft(e.target.value)}
                  placeholder="Square feet"
                  type="number"
                  min={100}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  required
                />
              </div>
              <button className="inline-flex items-center gap-2 rounded-lg bg-[#2E75B6] px-4 py-2 text-sm font-medium text-white hover:bg-[#1B2A4A]">
                Start Valuation <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}

          {step > 0 && step < 5 && (
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="space-y-2 text-sm">
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-lg bg-[#F2F2F2] px-3 py-2 text-slate-900">
                    {questions[step - 1]}
                  </div>
                </div>
                {answers.map((a, idx) => (
                  <div key={idx} className="flex justify-end">
                    <div className="max-w-[85%] rounded-lg bg-[#1B2A4A] px-3 py-2 text-white">{a}</div>
                  </div>
                ))}
              </div>
              <form onSubmit={nextQuestion} className="mt-4 flex gap-2">
                <input
                  value={currentAnswer}
                  onChange={(e) => setCurrentAnswer(e.target.value)}
                  placeholder="Type your answer..."
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  required
                />
                <button className="rounded-lg bg-[#2E75B6] px-4 py-2 text-sm font-medium text-white">Send</button>
              </form>
            </div>
          )}

          {loading && <p className="mt-4 text-sm text-slate-600">Generating valuation report...</p>}
          {error && <p className="mt-4 text-sm text-rose-600">{error}</p>}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-[#1B2A4A]">
            <Sparkles className="h-5 w-5" />
            <h2 className="text-xl font-semibold">Your Home Valuation Report</h2>
          </div>
          {!estimate ? (
            <p className="mt-4 text-sm text-slate-500">Complete the questions to generate your report.</p>
          ) : (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Estimated Value Range</p>
                <p className="mt-1 text-xl font-semibold text-[#1B2A4A]">
                  {money(estimate.estimated_low)} - {money(estimate.estimated_mid)} - {money(estimate.estimated_high)}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Price / Sq Ft Comparison</p>
                <p className="mt-1 text-sm text-slate-800">
                  Your adjusted PPSF: <strong>${estimate.adjusted_price_per_sqft.toLocaleString()}</strong>
                </p>
                <p className="text-sm text-slate-700">
                  Area average PPSF: <strong>${estimate.area_avg_price_per_sqft.toLocaleString()}</strong>
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Market Trend ({estimate.area})</p>
                <p className="mt-1 text-sm font-medium text-slate-900">{trendLabel}</p>
              </div>

              <button
                type="button"
                onClick={() => setShowCtaForm(true)}
                className="mt-2 w-full rounded-lg bg-[#1B2A4A] px-4 py-2 text-sm font-medium text-white hover:bg-[#2E75B6]"
              >
                Get a detailed CMA from a licensed agent
              </button>

              {showCtaForm && (
                <form onSubmit={submitCtaLead} className="space-y-2 rounded-lg border border-slate-200 p-3">
                  <input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Full name"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                  <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Email"
                    type="email"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    required
                  />
                  <input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="Phone"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                  <button className="w-full rounded-lg bg-[#2E75B6] px-3 py-2 text-sm font-medium text-white">
                    Request CMA
                  </button>
                  {ctaStatus && <p className="text-xs text-slate-600">{ctaStatus}</p>}
                </form>
              )}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

