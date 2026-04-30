"use client";

import { FormEvent, useMemo, useState } from "react";

type LoanComparison = {
  loan_type: "fha" | "conventional" | "va";
  dti_limit: number;
  min_down_percent: number;
  pmi_included: boolean;
  min_credit_score: number;
  max_home_price: number;
  monthly_payment: {
    principal_interest: number;
    taxes: number;
    insurance: number;
    total_monthly: number;
  };
};

type CityAffordability = {
  city: string;
  median_home_price: number;
  affordability_percent_of_market: number;
  message: string;
};

type MortgageResponse = {
  max_home_price: number;
  monthly_payment_breakdown: {
    principal_interest: number;
    taxes: number;
    insurance: number;
    total_monthly: number;
  };
  mortgage_rate_30y: number;
  loan_comparisons: LoanComparison[];
  city_affordability_map: CityAffordability[];
  ai_recommendation: string;
  disclaimers: string[];
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function money(v?: number) {
  return `$${Math.round(v || 0).toLocaleString()}`;
}

export default function MortgagePage() {
  const [mode, setMode] = useState<"quick" | "chat">("quick");
  const [annualIncome, setAnnualIncome] = useState("120000");
  const [monthlyDebts, setMonthlyDebts] = useState("1200");
  const [downPayment, setDownPayment] = useState("30000");
  const [creditRange, setCreditRange] = useState("620-699");
  const [targetCities, setTargetCities] = useState("Austin,Miami,Chicago");

  const [chatMessages, setChatMessages] = useState<string[]>([
    "Tell me about your financial situation and I will help you understand your options.",
  ]);
  const [chatInput, setChatInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MortgageResponse | null>(null);
  const [leadStatus, setLeadStatus] = useState<string | null>(null);

  const parsedChat = useMemo(() => chatMessages.join(" ").toLowerCase(), [chatMessages]);

  function parseFromChat() {
    const income = parsedChat.match(/income[^0-9]*(\d{4,7})/i)?.[1] || annualIncome;
    const debts = parsedChat.match(/debt[^0-9]*(\d{2,6})/i)?.[1] || monthlyDebts;
    const savings = parsedChat.match(/savings[^0-9]*(\d{3,7})/i)?.[1] || downPayment;
    const credit = parsedChat.match(/(5\d\d|6\d\d|7\d\d|8\d\d)/)?.[1];
    const cities =
      parsedChat.match(/austin|miami|chicago|dallas|seattle|phoenix|atlanta|new york/g)?.join(",") ||
      targetCities;
    setAnnualIncome(String(income));
    setMonthlyDebts(String(debts));
    setDownPayment(String(savings));
    if (credit) setCreditRange(`${credit}+`);
    setTargetCities(cities);
  }

  async function calculate(e?: FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    setLeadStatus(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/mortgage/calculate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          annual_income: Number(annualIncome),
          monthly_debts: Number(monthlyDebts),
          down_payment: Number(downPayment),
          credit_score_range: creditRange,
          target_cities: targetCities.split(",").map((c) => c.trim()).filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error(`Calculation failed (${res.status})`);
      setResult((await res.json()) as MortgageResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to calculate.");
    } finally {
      setLoading(false);
    }
  }

  function sendChatMessage(e: FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const next = chatInput.trim();
    setChatMessages((prev) => [...prev, `You: ${next}`]);
    setChatInput("");
    const prompts = [
      "What is your annual income before taxes?",
      "What are your monthly debt payments?",
      "How much do you have saved for down payment?",
      "What is your credit score range and target cities?",
    ];
    const idx = Math.min((chatMessages.length - 1) % prompts.length, prompts.length - 1);
    setChatMessages((prev) => [...prev, `AI: ${prompts[idx]}`]);
  }

  async function captureLead() {
    const email = window.prompt("Enter email to continue with an agent:");
    if (!email || !result) return;
    setLeadStatus("Submitting...");
    try {
      const res = await fetch(`${API_BASE_URL}/api/leads/import/clay`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: "Mortgage Calculator Lead",
          email,
          intent: "buyer_primary",
          target_market: targetCities.split(",")[0]?.trim() || null,
          timeline: "1_3_months",
          property_type: "single_family",
          financing_type: "conventional",
          budget_max: result.max_home_price,
          consent_given: true,
          source: "mortgage_calculator",
        }),
      });
      if (!res.ok) throw new Error(`Lead submit failed (${res.status})`);
      setLeadStatus("Great — an agent will follow up with next steps.");
    } catch (err) {
      setLeadStatus(err instanceof Error ? err.message : "Lead submit failed.");
    }
  }

  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">AI Mortgage Affordability Calculator</h1>
          <p className="mt-1 text-sm text-slate-600">
            Use quick mode for instant results or AI chat for personalized affordability guidance.
          </p>
          <div className="mt-3 inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 text-sm">
            <button onClick={() => setMode("quick")} className={`rounded-md px-3 py-1.5 ${mode === "quick" ? "bg-white shadow-sm text-[#1B2A4A]" : "text-slate-600"}`}>Quick Calculator</button>
            <button onClick={() => setMode("chat")} className={`rounded-md px-3 py-1.5 ${mode === "chat" ? "bg-white shadow-sm text-[#1B2A4A]" : "text-slate-600"}`}>AI Chat Mode</button>
          </div>
        </section>

        {mode === "quick" ? (
          <form onSubmit={calculate} className="grid grid-cols-1 gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-2">
            <input value={annualIncome} onChange={(e) => setAnnualIncome(e.target.value)} type="number" className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="Annual income" />
            <input value={monthlyDebts} onChange={(e) => setMonthlyDebts(e.target.value)} type="number" className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="Monthly debts" />
            <input value={downPayment} onChange={(e) => setDownPayment(e.target.value)} type="number" className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="Down payment" />
            <input value={creditRange} onChange={(e) => setCreditRange(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-3 text-sm" placeholder="Credit score range" />
            <input value={targetCities} onChange={(e) => setTargetCities(e.target.value)} className="h-10 rounded-lg border border-slate-300 px-3 text-sm md:col-span-2" placeholder="Target cities (comma-separated)" />
            <button className="h-10 rounded-lg bg-[#1B2A4A] px-4 text-sm font-medium text-white hover:bg-[#2E75B6] md:col-span-2">{loading ? "Calculating..." : "Calculate Buying Power"}</button>
          </form>
        ) : (
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="space-y-2">
              {chatMessages.map((m, i) => (
                <div key={i} className={`flex ${m.startsWith("You:") ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${m.startsWith("You:") ? "bg-[#1B2A4A] text-white" : "bg-[#F2F2F2] text-slate-900"}`}>{m}</div>
                </div>
              ))}
            </div>
            <form onSubmit={sendChatMessage} className="mt-3 flex gap-2">
              <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} className="h-10 flex-1 rounded-lg border border-slate-300 px-3 text-sm" placeholder="Share your financial details..." />
              <button className="h-10 rounded-lg bg-[#2E75B6] px-4 text-sm font-medium text-white">Send</button>
            </form>
            <button onClick={() => { parseFromChat(); void calculate(); }} className="mt-3 h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 hover:bg-slate-50">
              Generate Personalized Recommendation
            </button>
          </section>
        )}

        {error && <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}

        {result && (
          <section className="space-y-4">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-[#1B2A4A]">Your Affordability Snapshot</h2>
              <p className="mt-1 text-sm text-slate-600">Current 30Y mortgage rate: {result.mortgage_rate_30y}%</p>
              <p className="mt-2 text-3xl font-semibold text-slate-900">{money(result.max_home_price)}</p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Principal + Interest</p><p className="font-semibold">{money(result.monthly_payment_breakdown.principal_interest)}</p></div>
                <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Taxes</p><p className="font-semibold">{money(result.monthly_payment_breakdown.taxes)}</p></div>
                <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Insurance/PMI</p><p className="font-semibold">{money(result.monthly_payment_breakdown.insurance)}</p></div>
                <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">Total Monthly</p><p className="font-semibold">{money(result.monthly_payment_breakdown.total_monthly)}</p></div>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-[#1B2A4A]">FHA vs Conventional vs VA</h3>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="py-2">Loan</th><th>Max Home Price</th><th>DTI</th><th>Min Down</th><th>PMI</th><th>Min Credit</th><th>Total Monthly</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.loan_comparisons.map((l) => (
                      <tr key={l.loan_type} className="border-b border-slate-100">
                        <td className="py-2 uppercase">{l.loan_type}</td>
                        <td>{money(l.max_home_price)}</td>
                        <td>{Math.round(l.dti_limit * 100)}%</td>
                        <td>{(l.min_down_percent * 100).toFixed(1)}%</td>
                        <td>{l.pmi_included ? "Included" : "No PMI"}</td>
                        <td>{l.min_credit_score}+</td>
                        <td>{money(l.monthly_payment.total_monthly)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-[#1B2A4A]">Your Buying Power by City</h3>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                {result.city_affordability_map.map((c) => (
                  <div key={c.city} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-sm font-semibold text-slate-900">{c.city}</p>
                    <p className="text-xs text-slate-600">Median: {money(c.median_home_price)}</p>
                    <p className="mt-1 text-sm text-[#1B2A4A]">{c.message}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="text-base font-semibold text-[#1B2A4A]">AI Recommendation</h3>
              <p className="mt-2 text-sm leading-6 text-slate-700">{result.ai_recommendation}</p>
              <button onClick={captureLead} className="mt-4 rounded-lg bg-[#1B2A4A] px-4 py-2 text-sm font-medium text-white hover:bg-[#2E75B6]">
                Ready to start looking? Chat with our agent
              </button>
              {leadStatus && <p className="mt-2 text-sm text-slate-600">{leadStatus}</p>}
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                {result.disclaimers.map((d) => (
                  <p key={d}>• {d}</p>
                ))}
              </div>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

