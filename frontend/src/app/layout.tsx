"use client";

import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import React, { useMemo, useState } from "react";
import {
  BarChart3,
  Calculator,
  Search,
  Gavel,
  Home,
  MapPinned,
  Menu,
  MessageSquare,
  Radar,
  Settings,
  Users,
  X,
} from "lucide-react";
import { SessionProvider, signOut, useSession } from "next-auth/react";

const PUBLIC_NAV_ITEMS = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/deals", label: "Deal Finder", icon: Search },
  { href: "/foreclosures", label: "Foreclosures", icon: Gavel },
  { href: "/valuation", label: "Home Valuation", icon: Home },
  { href: "/neighborhood", label: "Neighborhood Reports", icon: MapPinned },
  { href: "/mortgage", label: "Mortgage Calculator", icon: Calculator },
];

const PRIVATE_NAV_ITEMS = [
  { href: "/dashboard", label: "Lead Dashboard", icon: Users },
  { href: "/analytics", label: "Market Analytics", icon: BarChart3 },
  { href: "/signals", label: "Lead Signals", icon: Radar },
  { href: "/settings", label: "Settings", icon: Settings },
];

const NAV_ITEMS = [...PUBLIC_NAV_ITEMS, ...PRIVATE_NAV_ITEMS];

const MOBILE_TAB_ITEMS = NAV_ITEMS.filter(
  (item) => item.href === "/chat" || item.href === "/dashboard" || item.href === "/analytics" || item.href === "/settings"
);

function LayoutInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const companyName = process.env.NEXT_PUBLIC_COMPANY_NAME || "Khatri Realty";

  const { data: session, status } = useSession();

  const userName = session?.user?.name ?? (status === "loading" ? "Loading..." : "Guest");
  const role = session?.user?.role ?? "viewer";
  const roleLabel = role === "admin" ? "Admin" : role === "agent" ? "Agent" : "Viewer";

  const initials = useMemo(() => {
    const parts = userName
      .split(" ")
      .map((p) => p.trim())
      .filter(Boolean);
    if (!parts.length) return "U";
    return parts
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("");
  }, [userName]);

  // Auth screen layout: no sidebar/nav so the card stays centered.
  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
    <>
      <div className="min-h-screen md:flex">
        <button
          type="button"
          aria-label="Toggle menu"
          onClick={() => setMobileOpen((v) => !v)}
          className="fixed left-3 top-3 z-50 rounded-md border border-slate-300 bg-white p-2 shadow md:hidden"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>

        <aside
          className={`fixed inset-y-0 left-0 z-40 w-16 border-r border-white/10 bg-[#1B2A4A] text-white transition-transform duration-200 md:static md:w-60 md:translate-x-0 ${
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex h-full flex-col">
            <div className="border-b border-white/10 px-3 py-4">
              <div className="text-sm font-semibold md:text-lg">
                <span className="hidden md:inline">{companyName}</span>
                <span className="inline md:hidden">KR</span>
              </div>
              <div className="text-[11px] text-slate-200/80 md:text-xs">
                <span className="hidden md:inline">Lead Intelligence</span>
                <span className="inline md:hidden">Intel</span>
              </div>
            </div>

            <nav className="flex-1 space-y-1 px-2 py-3">
              {PUBLIC_NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                      active
                        ? "bg-white/10 text-white"
                        : "text-blue-100 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    <span
                      aria-hidden
                      className={`absolute left-0 top-1/2 h-8 -translate-y-1/2 rounded-r-md ${
                        active ? "block border-l-4 border-[#2E75B6]" : "block border-l-4 border-transparent"
                      }`}
                    />
                    <Icon className="h-4 w-4" />
                    <span className="hidden md:inline">{item.label}</span>
                  </Link>
                );
              })}

              <div className="my-2 border-t border-white/10" />

              {PRIVATE_NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition ${
                      active
                        ? "bg-white/10 text-white"
                        : "text-blue-100 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    <span
                      aria-hidden
                      className={`absolute left-0 top-1/2 h-8 -translate-y-1/2 rounded-r-md ${
                        active ? "block border-l-4 border-[#2E75B6]" : "block border-l-4 border-transparent"
                      }`}
                    />
                    <Icon className="h-4 w-4" />
                    <span className="hidden md:inline">{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="border-t border-white/10 px-3 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2E75B6] text-sm font-semibold">
                  {initials}
                </div>
                <div className="hidden md:block">
                  <p className="text-sm font-medium">{userName}</p>
                  <p className="text-xs text-slate-200/80">{roleLabel}</p>
                </div>
              </div>

              {session && (
                <button
                  type="button"
                  onClick={() => signOut({ callbackUrl: "/login" })}
                  className="mt-3 w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-white hover:bg-white/10"
                >
                  Logout
                </button>
              )}
            </div>
          </div>
        </aside>

        <main className="min-h-screen flex-1 pb-20 md:pb-0">{children}</main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white md:hidden">
        <div className="grid grid-cols-4">
          {MOBILE_TAB_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center justify-center py-2 text-[11px] ${
                  active ? "text-[#2E75B6]" : "text-slate-500"
                }`}
              >
                <Icon className="mb-1 h-4 w-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close menu backdrop"
          className="fixed inset-0 z-30 bg-black/30 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}
    </>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-[#FAFAFA] text-slate-900">
        <SessionProvider>{/* provides session to the sidebar */}
          <LayoutInner>{children}</LayoutInner>
        </SessionProvider>
      </body>
    </html>
  );
}

