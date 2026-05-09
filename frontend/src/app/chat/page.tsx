"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, SendHorizontal, ImagePlus, MapPin, Calendar as CalendarIcon, RefreshCw, Database, TrendingUp } from "lucide-react";
import { BudgetSlider, PropertyCarousel, MarketStats, ProgressStepper, BookingWidget, WhatsAppWidget, QuickReplies, MapModal } from "./widgets";

type Role = "user" | "assistant";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  widget?: any;
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
  widget?: any;
  recommendations?: any[];
};

const NAVY = "#1B2A4A";
const BLUE = "#2E75B6";
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

function getRoutingStatus(bucket?: "hot" | "warm" | "cold" | null, destination?: string | null) {
  if (destination === "google_sheets") {
    return { label: "Routed to CRM", cls: "text-emerald-400" };
  }
  if (destination === "blocked" && bucket === "hot") {
    return { label: "Blocked", cls: "text-rose-400" };
  }
  if (bucket === "warm") {
    return { label: "Nurture Queue", cls: "text-amber-400" };
  }
  if (bucket === "cold") {
    return { label: "Stored", cls: "text-slate-300" };
  }
  return { label: destination || "Pending", cls: "text-slate-200" };
}

export default function ChatPage() {
  const router = useRouter();
  const companyName = process.env.NEXT_PUBLIC_COMPANY_NAME || "810 Realty";
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
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [isMapOpen, setIsMapOpen] = useState(false);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const existing = window.localStorage.getItem("chat_session_id");
    if (existing) {
      setSessionId(existing);
      fetchHistory(existing);
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
  const routingStatus = useMemo(
    () => getRoutingStatus(pipelineSummary?.bucket ?? null, pipelineSummary?.destination ?? null),
    [pipelineSummary?.bucket, pipelineSummary?.destination]
  );

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

  async function fetchHistory(sid: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/history/${sid}`);
      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data) && data.length > 0) {
          setMessages(data.map((m: any, i: number) => ({
            id: `h-${i}`,
            role: m.role,
            content: m.content,
            widget: m.metadata?.widget
          })));
        }

      }
    } catch (err) {
      console.error("Failed to fetch history:", err);
    }
  }

  const [syncing, setSyncing] = useState(false);

  const handleSyncScraper = async () => {
    setSyncing(true);
    try {
      const inferredCity =
        leadProfile.target_market?.trim() || leadProfile.preferred_locations?.[0]?.trim() || "";
      if (!inferredCity) {
        router.push("/scraper");
        return;
      }

      const listingType = leadProfile.intent === "seller" ? "sale" : "rent";
      const response = await fetch(
        `${API_BASE_URL}/api/scraper/jobs?city=${encodeURIComponent(inferredCity)}&listing_type=${listingType}`,
        { method: "POST" }
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        alert(`Error: ${err?.detail || "Unable to launch scraper job."}`);
        return;
      }
      alert(`Scraper job launched for ${inferredCity} (${listingType}).`);
    } catch (err) {
      console.error("Sync failed", err);
      alert("Network error: Could not connect to the scraper service.");
    } finally {
      setSyncing(false);
    }
  };

  const resetChat = () => {
    const newSid = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(newSid);
    localStorage.setItem("chat_session_id", newSid);
    setMessages([{
      id: "welcome",
      role: "assistant",
      content: `Hi! I am your ${companyName} AI assistant. Tell me what you are looking for and I will help you get started.`,
    }]);
    setLeadProfile({});
    setRecommendations([]);
    setPipelineSummary(null);
    setError(null);
  };

  async function onSend(e?: FormEvent, customText?: string) {
    if (e) e.preventDefault();
    const trimmed = (customText || input).trim();
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
        widget: data.widget,
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
      if (data.recommendations) {
        setRecommendations(data.recommendations);
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

  return (
    <main className="min-h-screen bg-white">
      <div className="mx-auto flex h-screen max-w-7xl gap-4 p-4 md:gap-6 md:p-6">
        <section className="flex w-full flex-col rounded-xl border border-slate-200 bg-white shadow-sm md:w-[70%]">
          <header className="flex h-16 items-center justify-between border-b border-slate-100 bg-white px-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 shadow-lg shadow-blue-200">
                <TrendingUp className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-black tracking-tight" style={{ color: NAVY }}>
                  KHATRI REALTY AI
                </h1>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">US REAL ESTATE INTELLIGENCE</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <button 
                onClick={resetChat}
                className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-600 transition-all hover:border-blue-600 hover:text-blue-600 hover:shadow-md active:scale-95"
              >
                <SendHorizontal className="h-3 w-3 rotate-180" />
                New Chat
              </button>
              <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 border border-emerald-100">
                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[10px] font-black text-emerald-700 uppercase">Live Intel Active</span>
              </div>
            </div>
          </header>

          <div ref={scrollerRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4 md:px-5">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className="flex flex-col gap-2 max-w-[85%] md:max-w-[75%] items-start">
                  <div
                    className={`rounded-2xl px-4 py-2 text-sm leading-6 shadow-sm ${
                      msg.role === "user" ? "text-white self-end" : "bg-slate-100 text-slate-800"
                    }`}
                    style={msg.role === "user" ? { backgroundColor: NAVY } : undefined}
                  >
                    {msg.content}
                  </div>
                  {msg.widget && (
                    <div className="w-full">
                      {msg.widget.type === "budget_slider" && <BudgetSlider {...msg.widget} onSelect={(val: number) => {
                        setInput(`My budget is $${val.toLocaleString()}`);
                      }} />}
                      {msg.widget.type === "property_carousel" && <PropertyCarousel {...msg.widget} onSelect={(id: string) => setInput(`I'm interested in property ${id || "this listing"}`)} />}
                      {msg.widget.type === "market_stats" && <MarketStats {...msg.widget} />}
                      {msg.widget.type === "progress_stepper" && <ProgressStepper {...msg.widget} />}
                      {msg.widget.type === "booking" && <BookingWidget {...msg.widget} onBook={(slot: string) => onSend(undefined, `I'd like to book a slot for ${new Date(slot).toLocaleString()}`)} />}
                      {msg.widget.type === "whatsapp" && <WhatsAppWidget {...msg.widget} />}
                      {msg.widget.type === "quick_replies" && <QuickReplies {...msg.widget} onSelect={(val: string) => onSend(undefined, val)} />}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {typing && (
              <div className="flex justify-start">
                <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-100 px-4 py-2 text-sm text-slate-600">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  AI is typing...
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-slate-200 p-4 md:p-5">
            {error && (
              <div className="mb-3 flex items-center gap-2 rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700">
                <AlertCircle className="h-4 w-4" />
                {error}
              </div>
            )}
            <form onSubmit={(e) => onSend(e)} className="flex items-center gap-2">
              <div className="flex gap-1 mr-1">
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) alert(`Image "${file.name}" selected for upload (Simulation)`);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="p-2 text-slate-400 hover:text-blue-600 transition-colors rounded-lg hover:bg-slate-50"
                >
                  <ImagePlus className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={() => setIsMapOpen(true)}
                  className="p-2 text-slate-400 hover:text-blue-600 transition-colors rounded-lg hover:bg-slate-50"
                >
                  <MapPin className="h-5 w-5" />
                </button>
              </div>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message..."
                className="h-11 flex-1 rounded-lg border border-slate-300 px-3 text-sm outline-none ring-0 placeholder:text-slate-400 focus:border-blue-400"
              />
              <button
                type="submit"
                disabled={typing || !input.trim()}
                className="inline-flex h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60 transition-all active:scale-95"
                style={{ backgroundColor: BLUE }}
              >
                <SendHorizontal className="h-4 w-4" />
                <span className="hidden sm:inline">Send</span>
              </button>
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
                className="mt-1 inline-block font-medium text-blue-700 hover:underline"
              >
                Fair Housing Notice
              </a>
            </div>
          </div>
        </section>

        <aside className="hidden h-full w-[30%] overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:block">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold" style={{ color: NAVY }}>
              Lead Intelligence
            </h2>
            {leadProfile.consent_given ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : (
              <AlertCircle className="h-4 w-4 text-rose-500" />
            )}
          </div>

          <div className="mt-6 space-y-6">
            {/* Scraper Control Panel */}
            <div className="rounded-xl border border-blue-100 bg-blue-50/30 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-blue-600" />
                  <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500">Data Intelligence</h3>
                </div>
                <div className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
              </div>
              <div className="flex flex-col gap-2">
                <button 
                  onClick={handleSyncScraper}
                  disabled={syncing}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-white border border-blue-200 py-2.5 text-xs font-bold text-blue-600 transition-all hover:bg-blue-600 hover:text-white disabled:opacity-50 group"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
                  {syncing ? "Syncing Feed..." : "Sync Scraper Pro"}
                </button>
                <button
                  onClick={() => router.push("/scraper")}
                  className="w-full py-2 bg-blue-600 text-white rounded-lg text-xs font-bold transition-all hover:bg-blue-700"
                >
                  Launch Scraper Panel
                </button>
                <a 
                  href="/signals"
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 text-xs font-bold text-white transition-all hover:bg-blue-700 shadow-sm hover:shadow-md active:scale-[0.98]"
                >
                  <Database className="h-3.5 w-3.5" />
                  Open Signals Dashboard
                </a>
              </div>
              <p className="mt-2 text-[10px] text-center text-slate-400 font-medium">Pull latest lead signals or review them in dashboard</p>

            </div>

            <div>
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Core Requirements</h3>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold text-slate-500 uppercase">Intent</p>
                  <p className="mt-0.5 text-xs font-semibold text-slate-800 truncate">{formatTitle(leadProfile.intent)}</p>
                </div>
                <div className="rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold text-slate-500 uppercase">Timeline</p>
                  <p className="mt-0.5 text-xs font-semibold text-slate-800 truncate">{formatTimeline(leadProfile.timeline)}</p>
                </div>
                <div className="col-span-2 rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold text-slate-500 uppercase">Budget Range</p>
                  <p className="mt-0.5 text-xs font-semibold text-slate-800">{formatBudget(leadProfile.budget_min, leadProfile.budget_max)}</p>
                </div>
                <div className="col-span-2 rounded-lg bg-slate-50 p-2.5">
                  <p className="text-[10px] font-bold text-slate-500 uppercase">Locations</p>
                  <p className="mt-0.5 text-xs font-semibold text-slate-800">
                    {leadProfile.preferred_locations?.length
                      ? leadProfile.preferred_locations.join(", ")
                      : "Not specified"}
                  </p>
                </div>
              </div>
            </div>

            {/* Financials Group */}
            <div>
              <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Financial Profile</h3>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-blue-50/50 p-2.5 border border-blue-100/50">
                  <p className="text-[10px] font-bold text-blue-600 uppercase">Financing</p>
                  <p className="mt-0.5 text-xs font-semibold text-blue-900">{formatTitle(leadProfile.financing_type)}</p>
                </div>
                <div className="rounded-lg bg-blue-50/50 p-2.5 border border-blue-100/50">
                  <p className="text-[10px] font-bold text-blue-600 uppercase">Pre-Approved</p>
                  <p className="mt-0.5 text-xs font-semibold text-blue-900">{preApprovalStatus}</p>
                </div>
              </div>
            </div>

            {/* AI Insights Group */}
            {pipelineSummary && (
              <div>
                <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400">AI Scoring & Routing</h3>
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-900 p-4 text-white">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-400">Heat Score</span>
                    <span className={`text-lg font-black ${pipelineSummary.bucket === 'hot' ? 'text-orange-400' : 'text-blue-400'}`}>
                      {pipelineSummary.score ?? "--"}/100
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-1000 ${pipelineSummary.bucket === 'hot' ? 'bg-orange-500' : 'bg-blue-500'}`}
                      style={{ width: `${pipelineSummary.score ?? 0}%` }}
                    />
                  </div>
                  <div className="mt-4 flex flex-col gap-1.5">
                    <div className="flex justify-between text-[10px]">
                      <span className="text-slate-400">Classification</span>
                      <span className="font-bold uppercase tracking-tight">{pipelineSummary.bucket}</span>
                    </div>
                    <div className="flex justify-between text-[10px]">
                      <span className="text-slate-400">Destination</span>
                      <span className={`font-bold ${routingStatus.cls}`}>{routingStatus.label}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Recommendations Section */}
            {recommendations && recommendations.length > 0 && (
              <div>
                <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-400">Top Recommendations</h3>
                <div className="mt-3 space-y-3">
                  {recommendations.map((prop) => (
                    <div 
                      key={prop.id} 
                      className="group overflow-hidden rounded-xl border border-slate-100 bg-white shadow-sm transition-all hover:border-blue-200 hover:shadow-md cursor-pointer"
                      onClick={() => onSend(undefined, `I'm interested in ${prop.title}`)}
                    >
                      <div className="relative h-24 w-full overflow-hidden">
                        <img 
                          src={prop.image_url} 
                          alt={prop.title} 
                          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110"
                        />
                        <div className="absolute top-2 right-2 rounded-md bg-white/90 px-2 py-1 text-[10px] font-bold text-blue-700 backdrop-blur-sm shadow-sm">
                          {prop.bedrooms} BR
                        </div>
                      </div>
                      <div className="p-2.5">
                        <p className="text-xs font-bold text-slate-800 line-clamp-1">{prop.title}</p>
                        <div className="mt-1 flex items-center justify-between">
                          <span className="text-[10px] text-slate-500 font-medium">{prop.area}</span>
                          <span className="text-xs font-black text-blue-600">
                            USD {(prop.price / 1000000).toFixed(1)}M
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>

      <MapModal 
        isOpen={isMapOpen} 
        onClose={() => setIsMapOpen(false)} 
        onSelect={(loc: string) => onSend(undefined, `I'm interested in properties in ${loc}`)} 
      />
    </main>
  );
}

