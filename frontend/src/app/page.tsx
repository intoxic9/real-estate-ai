export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FAFAFA] p-6">
      <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#2E75B6]">
          810 Realty Lead Intelligence
        </p>
        <h1 className="mt-3 text-4xl font-semibold text-[#1B2A4A]">
          Know your home value in minutes
        </h1>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-slate-600">
          Use our free AI-powered valuation tool to estimate your home using local market pricing,
          upgrades, and property condition.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <a
            href="/valuation"
            className="rounded-lg bg-[#1B2A4A] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#2E75B6]"
          >
            Free Home Valuation
          </a>
          <a
            href="/chat"
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Chat with AI Assistant
          </a>
        </div>
      </div>
    </main>
  );
}

