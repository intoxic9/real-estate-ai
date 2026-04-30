"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, SendHorizontal, XCircle } from "lucide-react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";

type Role = "user" | "assistant";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
};

type LeadProfile = {
  intent?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  preferred_locations?: string[] | null;
  target_market?: string | null;
  timeline?: string | null;
  property_type?: string | null;
  financing_type?: string | null;
  is_first_time_buyer?: boolean | null;
  consent_given?: boolean | null;
};

type ChatApiResponse = {
  response: string;
  lead_profile?: LeadProfile | null;
  lead_profile_updates?: Partial<LeadProfile> | null;
  pipeline_complete?: boolean;
  score?: number | null;
  bucket?: "hot" | "warm" | "cold" | null;
  routed?: boolean;
  destination?: string | null;
  reason?: string | null;
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  ""
);

function labelOrPlaceholder(value: string | null | undefined, placeholder = "Not provided") {
  return value && value.trim().length > 0 ? value : placeholder;
}

function formatBudget(min?: number | null, max?: number | null) {
  if (typeof min === "number" && typeof max === "number") {
    return `$${min.toLocaleString()} - $${max.toLocaleString()}`;
  }
  if (typeof min === "number") return `$${min.toLocaleString()}+`;
  if (typeof max === "number") return `Up to $${max.toLocaleString()}`;
  return "Not provided";
}

function formatTimeline(value?: string | null) {
  if (!value) return "Not provided";
  return value.replaceAll("_", " ");
}

function formatTitle(value?: string | null) {
  if (!value) return "Not provided";
  return value
    .replaceAll("_", " ")
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function scoreClass(bucket?: string | null) {
  if (bucket === "hot") return "bg-emerald-100 text-emerald-700";
  if (bucket === "warm") return "bg-amber-100 text-amber-700";
  if (bucket === "cold") return "bg-slate-200 text-slate-700";
  return "bg-slate-100 text-slate-700";
}

export default function ChatPage() {
  const companyName = process.env.NEXT_PUBLIC_COMPANY_NAME || "Khatri Realty";
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        `Hi! I am your ${companyName} AI assistant. Tell me what you are looking for and I will help you get started.`,
    },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pipelineSummary, setPipelineSummary] = useState<ChatApiResponse | null>(null);
  const [leadProfile, setLeadProfile] = useState<LeadProfile>({});
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [prefillConsumed, setPrefillConsumed] = useState(false);

  useEffect(() => {
    const existing = window.localStorage.getItem("chat_session_id");
    if (existing) {
      setSessionId(existing);
      return;
    }
    const created =
      window.crypto?.randomUUID?.() ?? `session-${Date.now()}-${Math.floor(Math.random() * 9999)}`;
    window.localStorage.setItem("chat_session_id", created);
    setSessionId(created);
  }, []);

  useEffect(() => {
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, typing]);

  const preApprovalStatus = useMemo(() => {
    const joined = messages.map((m) => m.content.toLowerCase()).join(" ");
    if (joined.includes("pre-approved") || joined.includes("pre approved")) return "Yes";
    if (joined.includes("not pre-approved") || joined.includes("not pre approved")) return "No";
    return "Unknown";
  }, [messages]);

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

  async function onSend(e: FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || !sessionId || typing) return;

    setError(null);
    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setTyping(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: trimmed,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const data = await safeJson<ChatApiResponse>(response);
      const assistantMessage: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: data.response,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      if (data.lead_profile_updates) {
        setLeadProfile((prev) => ({
          ...prev,
          ...data.lead_profile_updates,
        }));
      }
      if (data.lead_profile) {
        setLeadProfile((prev) => ({
          ...prev,
          ...data.lead_profile,
        }));
      }

      if (data.pipeline_complete) {
        setPipelineSummary(data);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          content: "I hit an issue reaching the server. Please try again.",
        },
      ]);
    } finally {
      setTyping(false);
    }
  }

  useEffect(() => {
    if (!sessionId || prefillConsumed || typeof window === "undefined") return;
    const prefill = new URLSearchParams(window.location.search).get("prefill");
    if (!prefill || !prefill.trim()) return;
    setInput(prefill);
    setPrefillConsumed(true);
  }, [sessionId, prefillConsumed]);

  return (
    <main className="min-h-screen bg-[#FAFAFA]">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-4 p-4 md:flex-row md:gap-6 md:p-6">
        <section className="flex-1">
          <Card className="flex h-full min-h-[640px] flex-col rounded-xl border border-slate-200 bg-white">
            <CardHeader className="border-b border-slate-200 p-4 md:px-5 md:py-3">
              <CardTitle className="text-lg font-semibold text-[#1B2A4A]">Lead Intake Chat</CardTitle>
              <p className="mt-1 text-xs text-slate-500">Session: {sessionId || "Generating..."}</p>
            </CardHeader>

            <CardContent className="flex-1 overflow-y-auto px-4 py-4 md:px-5">
              <div ref={scrollerRef} className="space-y-3">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-lg px-4 py-2 text-sm leading-6 shadow-sm md:max-w-[75%] ${
                        msg.role === "user" ? "bg-[#1B2A4A] text-white" : "bg-[#F2F2F2] text-slate-900"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                ))}

                {typing && (
                  <div className="flex justify-start">
                    <div className="inline-flex items-center gap-2 rounded-lg bg-[#F2F2F2] px-4 py-2 text-sm text-slate-700">
                      <span className="text-slate-600">AI is typing</span>
                      <span className="inline-flex items-center gap-1" aria-label="Typing">
                        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "120ms" }} />
                        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "240ms" }} />
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>

            <div className="border-t border-slate-200 p-4 md:p-5">
              {error && (
                <div className="mb-3 flex items-center gap-2 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
              <form onSubmit={onSend} className="flex items-center gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message..."
                  className="h-11 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-blue-400 focus-visible:ring-2 focus-visible:ring-[#2E75B6] focus-visible:ring-offset-2"
                />
                <Button type="submit" disabled={typing || !input.trim()} size="lg">
                  <SendHorizontal className="h-4 w-4" />
                  Send
                </Button>
              </form>

              <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                <p>
                  This AI assistant provides general real estate information. It is not a licensed
                  real estate agent or mortgage broker. Consult a licensed professional for specific
                  advice.
                </p>
                <a
                  href="https://www.hud.gov/program_offices/fair_housing_equal_opp/fair_housing_act_overview"
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-block font-medium text-[#2E75B6] hover:underline"
                >
                  Fair Housing Notice
                </a>
              </div>
            </div>
          </Card>
        </section>

        <aside className="w-full md:w-[30%]">
          <Card className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-[#1B2A4A]">Live Lead Profile</h2>

            <div className="mt-4 space-y-3 text-sm">
              <div className="space-y-2">
                {[
                  ["Intent", formatTitle(leadProfile.intent)],
                  ["Budget", formatBudget(leadProfile.budget_min, leadProfile.budget_max)],
                  [
                    "Locations",
                    leadProfile.preferred_locations?.length
                      ? leadProfile.preferred_locations.join(", ")
                      : "Not provided",
                  ],
                  ["Target Market", labelOrPlaceholder(leadProfile.target_market)],
                  ["Timeline", formatTimeline(leadProfile.timeline)],
                  ["Property Type", formatTitle(leadProfile.property_type)],
                  ["Financing Type", formatTitle(leadProfile.financing_type)],
                  ["Pre-Approval", preApprovalStatus],
                ].map(([label, value]) => {
                  const empty = value === "Not provided";
                  return (
                    <div key={label} className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
                      <p className={`text-sm ${empty ? "text-slate-400" : "text-slate-900"}`}>
                        {value}
                      </p>
                    </div>
                  );
                })}
              </div>

              <div className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wide text-slate-500">Consent</p>
                <div className="flex items-center gap-2">
                  {leadProfile.consent_given ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      <span className="text-emerald-700">Granted</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 text-rose-500" />
                      <span className="text-rose-700">Not granted</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <p className="text-[11px] uppercase tracking-wide text-slate-500">First-Time Buyer</p>
                <div>
                  {leadProfile.is_first_time_buyer ? (
                    <span className="inline-flex rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">
                      Yes
                    </span>
                  ) : (
                    <span className="text-slate-400">Not provided</span>
                  )}
                </div>
              </div>

              {pipelineSummary && (
                <div className="mt-1 rounded-xl border border-slate-200 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                        Pipeline Summary
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Routing: {pipelineSummary.routed ? "Routed" : "Not routed"}
                        {pipelineSummary.destination ? ` (${pipelineSummary.destination})` : ""}
                      </p>
                    </div>
                    <Badge
                      className={`rounded-full px-3 py-2 text-sm font-semibold ${scoreClass(
                        pipelineSummary.bucket
                      )}`}
                    >
                      {pipelineSummary.score ?? "--"}
                    </Badge>
                  </div>

                  {pipelineSummary.reason && (
                    <p className="mt-2 text-xs text-slate-500">{pipelineSummary.reason}</p>
                  )}
                </div>
              )}
            </div>
          </Card>
        </aside>
      </div>
    </main>
  );
}

