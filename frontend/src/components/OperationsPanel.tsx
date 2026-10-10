import { useRef, useState } from 'react'

type EventRow = { agent?: string; message: string; colour?: string }
type MissionState = { done: boolean; events: EventRow[]; result?: { rows?: unknown[]; reviews?: { card: string; action: string }[]; notices?: { kind: string; lang: string; body: string }[]; error?: string } | null }

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) throw new Error((await response.text()) || response.statusText)
  return response.json() as Promise<T>
}

export default function OperationsPanel() {
  const [mission, setMission] = useState<MissionState | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const run = async () => {
    setBusy(true)
    setMission(null)
    const started = await json<{ mission_id: string }>('/api/mission', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mission: 'Audit the synthetic registry, review blocked pages, and prepare notices', max_docs: 15, year_from: 2018, year_to: 2020 }),
    })
    const poll = async () => {
      const state = await json<MissionState>(`/api/mission/${started.mission_id}`)
      setMission(state)
      if (state.done) { setBusy(false); return }
      timer.current = window.setTimeout(() => void poll(), 500)
    }
    void poll()
  }

  return <section className="mx-auto mt-8 max-w-7xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-700">v2–v5 workflow</p><h2 className="mt-1 text-lg font-semibold text-slate-900">Mission control</h2><p className="mt-1 text-sm text-slate-500">Orchestrator → Auditor → Reviewer → Notice. Deterministic scanning stays authoritative; notices remain drafts.</p></div>
      <button type="button" onClick={() => void run()} disabled={busy} className="rounded-lg bg-accent-700 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-accent-800 disabled:opacity-50">{busy ? 'Mission running locally…' : 'Run synthetic mission'}</button>
    </div>
    {mission && <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-2" aria-live="polite">{mission.events.map((event, i) => <div key={i} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm" style={{ borderLeft: `4px solid ${event.colour ?? '#64748b'}` }}><span className="font-semibold text-slate-800">{event.agent}</span><span className="text-slate-600"> — {event.message}</span></div>)}</div>
      {mission.result && <div className="space-y-3"><div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-700"><strong>{mission.result.rows?.length ?? 0}</strong> deeds audited · <strong>{mission.result.reviews?.length ?? 0}</strong> review cards · <strong>{mission.result.notices?.length ?? 0}</strong> draft notices</div>{mission.result.reviews?.map((review, i) => <div key={i} className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><strong>{review.action}</strong><p className="mt-1 text-amber-900">{review.card}</p></div>)}{mission.result.notices?.map((notice, i) => <details key={i} className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm"><summary className="cursor-pointer font-medium">{notice.kind} · {notice.lang}</summary><pre className="mt-2 whitespace-pre-wrap text-violet-950">{notice.body}</pre></details>)}</div>}
    </div>}
  </section>
}
