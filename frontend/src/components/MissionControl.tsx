import { useState } from 'react'

type State = { mission_id: string; done: boolean; events: { agent?: string; type?: string; message?: string; colour?: string }[]; result?: { report?: string; rows?: unknown[]; reviews?: unknown[]; notices?: unknown[] }; error?: string }

export default function MissionControl() {
  const [objective, setObjective] = useState('Audit synthetic registry exposure and prepare human-review drafts')
  const [maxDocs, setMaxDocs] = useState(10); const [state, setState] = useState<State | null>(null); const [busy, setBusy] = useState(false)
  async function start() {
    setBusy(true); setState(null)
    const response = await fetch('/api/missions', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mission:objective, max_docs:maxDocs, year_from:2018, year_to:2024})})
    if (!response.ok) { setBusy(false); return }
    const {mission_id} = await response.json(); const source = new EventSource(`/api/missions/${mission_id}/events`)
    const refresh = async () => { const next = await (await fetch(`/api/missions/${mission_id}`)).json(); setState(next); if (next.done) { source.close(); setBusy(false) } }
    ;['progress','complete'].forEach(kind => source.addEventListener(kind, refresh)); source.onerror = refresh
  }
  return <section className="mx-auto mt-8 max-w-7xl rounded-2xl border border-blue-200 bg-white p-6 shadow-sm"><div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">v4 mission control</p><h2 className="mt-1 text-lg font-semibold">Orchestrator → Auditor → Reviewer → Notice</h2><p className="text-sm text-slate-500">Synthetic-only workflow. Drafts are never sent automatically.</p></div><button onClick={()=>void start()} disabled={busy} className="rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{busy?'Mission running…':'Start mission'}</button></div><div className="mt-4 flex gap-3"><textarea value={objective} onChange={e=>setObjective(e.target.value)} className="min-h-16 flex-1 rounded-lg border p-3 text-sm"/><input aria-label="Maximum documents" type="number" min="1" max="120" value={maxDocs} onChange={e=>setMaxDocs(+e.target.value)} className="h-10 w-28 rounded-lg border p-2"/></div>{state&&<div className="mt-5 grid gap-5 lg:grid-cols-2"><div className="space-y-2">{state.events.map((e,i)=><div key={i} className="rounded border bg-slate-50 px-3 py-2 text-sm" style={{borderLeft:`4px solid ${e.colour??'#2563eb'}`}}><strong>{e.agent??e.type}</strong>{e.message&&` — ${e.message}`}</div>)}{state.error&&<p className="text-sm text-red-700">{state.error}</p>}</div><div className="rounded-lg bg-slate-50 p-4 text-sm"><p><strong>{state.result?.rows?.length??0}</strong> documents · <strong>{state.result?.reviews?.length??0}</strong> reviews · <strong>{state.result?.notices?.length??0}</strong> drafts</p>{state.result?.report&&<details className="mt-3"><summary className="cursor-pointer font-medium">Final Markdown report</summary><pre className="mt-2 whitespace-pre-wrap text-xs">{state.result.report}</pre></details>}</div></div>}</section>
}
