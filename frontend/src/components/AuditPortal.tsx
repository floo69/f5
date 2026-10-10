import { useEffect, useState } from 'react'

type Row = { doc_id: string; doc_no?: string; year?: number; thumbprints?: number; aadhaar?: number; decision?: string }
type Audit = { audit_id: string; done: boolean; error?: string | null; results: Row[]; events: { type: string; timestamp?: string; message?: string }[] }

export default function AuditPortal() {
  const [sro, setSro] = useState(''); const [from, setFrom] = useState(2018); const [to, setTo] = useState(2024); const [max, setMax] = useState(10)
  const [audit, setAudit] = useState<Audit | null>(null); const [busy, setBusy] = useState(false)
  const start = async () => {
    setBusy(true); setAudit(null)
    const response = await fetch('/api/audit', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({sro, year_from: from, year_to: to, max_docs: max}) })
    if (!response.ok) { setBusy(false); return }
    const { audit_id } = await response.json(); const source = new EventSource(`/api/audit/${audit_id}/events`)
    const refresh = async () => setAudit(await (await fetch(`/api/audit/${audit_id}`)).json())
    ;['audit_started','search_submitted','results_discovered','pdf_fetched','scan_completed','audit_completed','error','complete'].forEach(kind => source.addEventListener(kind, refresh))
    source.onerror = async () => { const state = await (await fetch(`/api/audit/${audit_id}`)).json(); setAudit(state); if (state.done) { source.close(); setBusy(false) } }
  }
  useEffect(() => () => {}, [])
  const rows = audit?.results ?? []
  return <section className="mx-auto mt-8 max-w-7xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-700">synthetic demonstration data</p><h2 className="mt-1 text-lg font-semibold">Audit Portal</h2><p className="text-sm text-slate-500">Allowlisted local registry audit with live progress.</p></div><button onClick={() => void start()} disabled={busy} className="rounded-lg bg-accent-700 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">{busy ? 'Audit running…' : 'Start audit'}</button></div>
    <div className="mt-5 grid gap-3 md:grid-cols-4"><select value={sro} onChange={e=>setSro(e.target.value)} className="rounded-lg border p-2"><option value="">All SRO offices</option><option>SRO Thiruvananthapuram</option><option>SRO Ernakulam</option><option>SRO Kottayam</option><option>SRO Thrissur</option><option>SRO Kozhikode</option></select><input type="number" value={from} onChange={e=>setFrom(+e.target.value)} className="rounded-lg border p-2" aria-label="Start year"/><input type="number" value={to} onChange={e=>setTo(+e.target.value)} className="rounded-lg border p-2" aria-label="End year"/><input type="number" min="1" max="120" value={max} onChange={e=>setMax(+e.target.value)} className="rounded-lg border p-2" aria-label="Maximum documents"/></div>
    {audit && <><div className="mt-5 grid gap-3 md:grid-cols-4"><div className="rounded-lg bg-slate-50 p-3"><strong>{rows.length}</strong><span className="ml-1 text-sm">reviewed</span></div><div className="rounded-lg bg-slate-50 p-3"><strong>{rows.filter(r=>(r.thumbprints??0)+(r.aadhaar??0)>0).length}</strong><span className="ml-1 text-sm">exposed deeds</span></div><div className="rounded-lg bg-slate-50 p-3"><strong>{rows.reduce((n,r)=>n+(r.thumbprints??0),0)}</strong><span className="ml-1 text-sm">thumbprints</span></div><div className="rounded-lg bg-slate-50 p-3"><strong>{rows.reduce((n,r)=>n+(r.aadhaar??0),0)}</strong><span className="ml-1 text-sm">Aadhaar findings</span></div></div><div className="mt-5 grid gap-5 lg:grid-cols-2"><div className="space-y-2" aria-live="polite">{audit.events.map((e,i)=><div key={i} className="rounded border bg-slate-50 px-3 py-2 text-sm"><span className="font-semibold">{e.type}</span>{e.message && ` — ${e.message}`}</div>)}{audit.error && <p className="text-sm text-red-700">{audit.error}</p>}</div><div className="overflow-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="p-2">Document</th><th className="p-2">Year</th><th className="p-2">Thumbprints</th><th className="p-2">Aadhaar</th><th className="p-2">Status</th></tr></thead><tbody>{rows.map(r=><tr key={r.doc_id} className="border-b"><td className="p-2">{r.doc_no ?? r.doc_id}</td><td className="p-2">{r.year}</td><td className="p-2">{r.thumbprints ?? 0}</td><td className="p-2">{r.aadhaar ?? 0}</td><td className="p-2">{r.decision ?? 'scanned'}</td></tr>)}</tbody></table></div></div></>}
  </section>
}
