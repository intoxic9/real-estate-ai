"use client";

import { CheckCircle2, ChevronLeft, ChevronRight, Phone, Calendar, Info, TrendingUp } from "lucide-react";
import { AlertCircle, MapPin } from "lucide-react";
import { useState } from "react";

export function BudgetSlider({ min_value, max_value, currency, onSelect }: any) {
  const { min_value: minValue = 50000, max_value: maxValue = 2000000, currency: curr = "USD" } = {
    min_value,
    max_value,
    currency,
  };
  const [val, setVal] = useState(minValue + (maxValue - minValue) / 2);
  return (
    <div className="mt-2 space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
        <span>Budget Range ({curr})</span>
      </div>
      <input
        type="range"
        min={minValue}
        max={maxValue}
        step={10000}
        value={val}
        onChange={(e) => setVal(Number(e.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-blue-600"
      />
      <div className="flex justify-between font-mono text-sm font-bold text-slate-800">
        <span>{curr} {(minValue ?? 50000).toLocaleString()}</span>
        <span className="text-blue-600">{curr} {(val ?? 500000).toLocaleString()}</span>
        <span>{curr} {(maxValue ?? 2000000).toLocaleString()}</span>
      </div>
      <button
        onClick={() => onSelect?.(val)}
        className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white transition-colors hover:bg-blue-700"
      >
        Confirm Budget
      </button>
    </div>
  );
}

export function PropertyCarousel({ properties = [], onSelect }: any) {
  const [index, setIndex] = useState(0);
  
  if (!properties || properties.length === 0) {
    return (
      <div className="mt-2 rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-500 shadow-sm">
        No properties available at the moment.
      </div>
    );
  }

  const p = properties[index] ?? {};

  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="relative aspect-video w-full bg-slate-100">
        {p.image_url ? (
          <img src={p.image_url} alt={p.title} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-400">No Image</div>
        )}
        <div className="absolute inset-0 flex items-center justify-between px-2">
          <button onClick={() => setIndex((i) => (i > 0 ? i - 1 : properties.length - 1))} className="rounded-full bg-white/80 p-1 shadow-md hover:bg-white"><ChevronLeft className="h-5 w-5" /></button>
          <button onClick={() => setIndex((i) => (i < properties.length - 1 ? i + 1 : 0))} className="rounded-full bg-white/80 p-1 shadow-md hover:bg-white"><ChevronRight className="h-5 w-5" /></button>
        </div>
      </div>
      <div className="p-4">
        <h3 className="font-bold text-slate-800">{p.title ?? "Untitled property"}</h3>
        <p className="text-xs text-slate-500">{p.location ?? "Location unavailable"}</p>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-lg font-black text-blue-700">${Number(p.price ?? 0).toLocaleString()}</span>
          <div className="flex gap-3 text-xs text-slate-600">
            <span>{p.beds ?? 0} bds</span>
            <span>{p.baths ?? 0} ba</span>
            <span>{p.sqft ?? 0} sqft</span>
          </div>
        </div>
        <button
          onClick={() => onSelect?.(p.id ?? "")}
          className="mt-4 w-full rounded-lg border border-blue-600 py-2 text-sm font-semibold text-blue-600 transition-all hover:bg-blue-50"
        >
          View Details
        </button>
      </div>
    </div>
  );
}

export function MarketStats({ area, median_price, price_change_pct, days_on_market, inventory_count }: any) {
  const {
    area: safeArea = "Unknown Area",
    median_price: medianPrice = 0,
    price_change_pct: priceChangePct = 0,
    days_on_market: daysOnMarket = 0,
    inventory_count: _inventoryCount = 0,
  } = { area, median_price, price_change_pct, days_on_market, inventory_count };
  return (
    <div className="mt-2 space-y-3 rounded-xl border border-slate-200 bg-blue-50/50 p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-blue-600" />
        <h3 className="text-sm font-bold text-slate-800">Market Insights: {safeArea}</h3>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-white p-2 shadow-sm">
          <p className="text-[10px] uppercase text-slate-500">Median Price</p>
          <p className="text-sm font-bold text-slate-800">${Number(medianPrice).toLocaleString()}</p>
          <p className={`text-[10px] ${priceChangePct >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
            {priceChangePct >= 0 ? "+" : ""}{priceChangePct}% YoY
          </p>
        </div>
        <div className="rounded-lg bg-white p-2 shadow-sm">
          <p className="text-[10px] uppercase text-slate-500">Days on Market</p>
          <p className="text-sm font-bold text-slate-800">{daysOnMarket} days</p>
          <p className="text-[10px] text-slate-400">Market Speed: Fast</p>
        </div>
      </div>
    </div>
  );
}

export function ProgressStepper({ steps, current_step_index }: any) {
  const safeSteps = Array.isArray(steps) && steps.length ? steps : ["Intro", "Details", "Complete"];
  const safeStepIndex = typeof current_step_index === "number" ? current_step_index : 0;
  return (
    <div className="mt-2 flex w-full items-center justify-between px-2">
      {safeSteps.map((step: string, i: number) => (
        <div key={step} className="flex flex-col items-center gap-1">
          <div className={`h-2 w-2 rounded-full ${i <= safeStepIndex ? "bg-blue-600" : "bg-slate-300"}`} />
          <span className={`text-[10px] ${i <= safeStepIndex ? "font-bold text-blue-700" : "text-slate-400"}`}>{step}</span>
        </div>
      ))}
    </div>
  );
}

export function BookingWidget({ agent_name = "Agent", available_slots = [], onBook }: any) {
  const safeAgentName = agent_name || "Agent";
  const safeSlots = Array.isArray(available_slots) ? available_slots : [];
  return (
    <div className="mt-2 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 font-bold">
          {safeAgentName ? safeAgentName[0] : "A"}
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-800">Book with {safeAgentName}</h3>
          <p className="text-[10px] text-slate-500">Expert Lead Consultant</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {safeSlots.map((slot: string) => (
          <button
            key={slot}
            onClick={() => onBook?.(slot)}
            className="rounded-lg border border-slate-200 py-1.5 text-xs transition-all hover:border-blue-500 hover:text-blue-600"
          >
            {new Date(slot).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </button>
        ))}
      </div>
    </div>
  );
}

export function WhatsAppWidget({ phone_number, message }: any) {
  const safePhone = String(phone_number ?? "").replace(/\D/g, "");
  const safeMessage = String(message ?? "Hi, I would like more information.");
  const url = `https://wa.me/${safePhone}?text=${encodeURIComponent(safeMessage)}`;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="mt-2 flex items-center justify-center gap-2 rounded-xl bg-[#25D366] py-3 text-sm font-bold text-white shadow-md transition-transform hover:scale-[1.02] active:scale-[0.98]"
    >
      <Phone className="h-4 w-4" />
      Contact Agent on WhatsApp
    </a>
  );
}

export function QuickReplies({ options, onSelect }: any) {
  const safeOptions = Array.isArray(options) ? options : [];
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {safeOptions.map((opt: any, idx: number) => {
        const value =
          typeof opt === "string"
            ? opt
            : (opt?.value ?? opt?.label ?? `option-${idx}`);
        const label =
          typeof opt === "string"
            ? opt
            : (opt?.label ?? opt?.value ?? "Option");
        return (
        <button
          key={String(value)}
          onClick={() => onSelect?.(String(value))}
          className="rounded-full border border-blue-600 bg-white px-4 py-1.5 text-xs font-semibold text-blue-600 transition-all hover:bg-blue-600 hover:text-white"
        >
          {String(label)}
        </button>
      )})}
    </div>
  );
}

export function MapModal({ isOpen, onClose, onSelect }: any) {
  const [region, setRegion] = useState<"Dubai" | "USA">("Dubai");
  const [selectedLoc, setSelectedLoc] = useState<string>("Dubai Marina");
  const [searchQuery, setSearchQuery] = useState("");
  
  if (!isOpen) return null;
  
  const dubaiLocations = [
    { name: "Dubai Marina", lat: 25.0819, lng: 55.1367 },
    { name: "Downtown Dubai", lat: 25.1972, lng: 55.2744 },
    { name: "Palm Jumeirah", lat: 25.1124, lng: 55.1390 },
    { name: "Business Bay", lat: 25.1844, lng: 55.2725 },
    { name: "JVC", lat: 25.0567, lng: 55.2081 },
  ];

  const usaLocations = [
    { name: "Miami, FL", lat: 25.7617, lng: -80.1918 },
    { name: "New York, NY", lat: 40.7128, lng: -74.0060 },
    { name: "Austin, TX", lat: 30.2672, lng: -97.7431 },
    { name: "Los Angeles, CA", lat: 34.0522, lng: -118.2437 },
    { name: "San Francisco, CA", lat: 37.7749, lng: -122.4194 },
  ];

  const predefined = region === "Dubai" ? dubaiLocations : usaLocations;
  const isCustom = !predefined.some(l => l.name === selectedLoc);
  
  const currentLoc = predefined.find(l => l.name === selectedLoc) || { name: selectedLoc, lat: predefined[0].lat, lng: predefined[0].lng };
  
  // For custom locations, we just search by name in the embed
  const mapUrl = isCustom 
    ? `https://www.google.com/maps/embed/v1/place?key=REPLACE_WITH_KEY_IF_AVAILABLE&q=${encodeURIComponent(selectedLoc)}`
    : `https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d3613.6!2d${currentLoc.lng}!3d${currentLoc.lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e0!3m2!1sen!2sae!4v1714400000000!5m2!1sen!2sae&q=${encodeURIComponent(selectedLoc)}`;

  // Use a simple search query embed if no API key is available for custom search
  const finalMapUrl = isCustom 
    ? `https://maps.google.com/maps?q=${encodeURIComponent(selectedLoc)}&t=&z=13&ie=UTF8&iwloc=&output=embed`
    : mapUrl;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="flex h-[85vh] w-full max-w-6xl overflow-hidden rounded-3xl bg-white shadow-2xl animate-in fade-in zoom-in duration-300">
        {/* Sidebar Selection */}
        <div className="w-80 border-r border-slate-100 bg-slate-50/50 p-6 flex flex-col">
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="bg-blue-600 p-2 rounded-xl">
                <MapPin className="h-5 w-5 text-white" />
              </div>
              <h2 className="text-lg font-bold text-slate-800">Global Search</h2>
            </div>
            
            {/* Custom Search Bar */}
            <div className="relative mb-4">
              <input 
                type="text"
                placeholder="Search any area..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && searchQuery.trim()) {
                    setSelectedLoc(searchQuery.trim());
                  }
                }}
                className="w-full pl-3 pr-10 py-3 rounded-xl border border-slate-200 bg-white text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all outline-none"
              />
              <button 
                onClick={() => searchQuery.trim() && setSelectedLoc(searchQuery.trim())}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-slate-400 hover:text-blue-600 transition-colors"
              >
                <TrendingUp className="h-4 w-4" />
              </button>
            </div>

            {/* Region Toggle */}
            <div className="flex p-1 bg-slate-200 rounded-xl">
              <button 
                onClick={() => { setRegion("Dubai"); setSelectedLoc("Dubai Marina"); }}
                className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${region === "Dubai" ? "bg-white text-blue-600 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Dubai
              </button>
              <button 
                onClick={() => { setRegion("USA"); setSelectedLoc("Miami, FL"); }}
                className={`flex-1 py-2 text-xs font-bold rounded-lg transition-all ${region === "USA" ? "bg-white text-blue-600 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                USA
              </button>
            </div>
          </div>
          
          <div className="space-y-1 flex-1 overflow-y-auto pr-2">
            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Quick Picks</p>
            {predefined.map((loc) => (
              <button
                key={loc.name}
                onClick={() => setSelectedLoc(loc.name)}
                className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all ${
                  selectedLoc === loc.name 
                    ? "bg-white border-blue-600 shadow-sm text-blue-700 font-bold" 
                    : "bg-transparent border-transparent text-slate-500 hover:bg-slate-100"
                }`}
              >
                <span className="text-sm">{loc.name}</span>
                {selectedLoc === loc.name && <CheckCircle2 className="h-4 w-4" />}
              </button>
            ))}
            
            {isCustom && (
              <div className="mt-4">
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 px-1">Custom Result</p>
                <div className="w-full flex items-center justify-between p-3 rounded-xl border bg-white border-orange-500 shadow-sm text-orange-700 font-bold">
                  <span className="text-sm truncate pr-2">{selectedLoc}</span>
                  <CheckCircle2 className="h-4 w-4" />
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 pt-6 border-t border-slate-200">
            <button 
              onClick={() => {
                onSelect(selectedLoc);
                onClose();
              }}
              className="w-full bg-slate-900 py-4 rounded-xl text-white font-bold hover:bg-slate-800 transition-colors shadow-lg shadow-slate-200 active:scale-95"
            >
              Set as Target Area
            </button>
          </div>
        </div>

        {/* Map View */}
        <div className="relative flex-1 bg-slate-100">
          <div className="absolute top-4 right-4 z-10">
             <button onClick={onClose} className="bg-white/90 backdrop-blur-md rounded-full p-2 shadow-lg hover:bg-white text-slate-400 hover:text-slate-600 transition-all">
                <AlertCircle className="h-6 w-6 rotate-45" />
             </button>
          </div>
          
          <iframe
            src={finalMapUrl}
            width="100%"
            height="100%"
            style={{ border: 0 }}
            allowFullScreen={true}
            loading="lazy"
            className="grayscale-[0.1] brightness-[0.98]"
          ></iframe>

          <div className="absolute bottom-6 left-6 right-6 bg-white/95 backdrop-blur-md p-5 rounded-2xl shadow-xl border border-white/20 flex items-center justify-between">
             <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Active Selection</p>
                <p className="text-lg font-black text-slate-900">{selectedLoc}</p>
             </div>
             <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-[10px] font-bold text-slate-500 bg-slate-100 px-4 py-2 rounded-full">
                   <TrendingUp className="h-3 w-3" />
                   <span>ACTIVE INTELLIGENCE</span>
                </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
