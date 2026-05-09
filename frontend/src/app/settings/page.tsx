import { CheckCircle2, KeyRound, ShieldCheck, ToggleLeft, ToggleRight } from "lucide-react";

export default function SettingsPage() {
  return (
    <main className="min-h-screen bg-[#FAFAFA] p-4 md:p-6">
      <div className="mx-auto max-w-4xl space-y-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#1B2A4A]">Settings</h1>
          <p className="mt-1 text-xs text-slate-500">Manage API access, compliance preferences, and notifications.</p>
        </div>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-[#2E75B6]" />
            <h2 className="text-sm font-semibold text-slate-800">API Key Configuration</h2>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              className="rounded border border-slate-300 px-3 py-2 text-sm"
              placeholder="Groq API key"
            />
            <input
              className="rounded border border-slate-300 px-3 py-2 text-sm"
              placeholder="Google API key (optional)"
            />
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Google Sheets Connection</h2>
          <div className="flex items-center gap-2 text-sm text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Connected (placeholder)
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-slate-800">Notification Preferences</h2>
          <div className="space-y-2 text-sm text-slate-700">
            <label className="flex items-center justify-between">
              <span>Email alerts for hot leads</span>
              <ToggleRight className="h-5 w-5 text-[#2E75B6]" />
            </label>
            <label className="flex items-center justify-between">
              <span>Daily pipeline summary</span>
              <ToggleLeft className="h-5 w-5 text-slate-400" />
            </label>
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-2 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-[#2E75B6]" />
            <h2 className="text-sm font-semibold text-slate-800">PDPL Compliance Settings</h2>
          </div>
          <div className="space-y-3 text-sm">
            <label className="block">
              <span className="mb-1 block text-slate-700">Data retention period (days)</span>
              <input
                type="number"
                defaultValue={90}
                className="w-40 rounded border border-slate-300 px-3 py-2"
              />
            </label>
            <label className="flex items-center justify-between text-slate-700">
              <span>Auto-delete expired lead data</span>
              <ToggleRight className="h-5 w-5 text-[#2E75B6]" />
            </label>
          </div>
        </section>
      </div>
    </main>
  );
}
