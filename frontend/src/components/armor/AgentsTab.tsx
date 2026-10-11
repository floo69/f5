import { useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS, ICONS2 } from '../helpers'
import { CopyButton, Icon } from '../ui'
import { btnPrimary, btnSecondary, card } from './styles'

const STEP: Record<armor.AgentStep, { icon: string; ring: string; label: string }> = {
  scan: { icon: ICONS2.scan, ring: 'bg-accent-50 text-accent-700 ring-accent-100', label: 'Scanning' },
  found: { icon: ICONS.alert, ring: 'bg-red-50 text-red-600 ring-red-100', label: 'Found a problem' },
  lock: { icon: ICONS.lock, ring: 'bg-saffron-50 text-saffron-700 ring-saffron-100', label: 'Your turn' },
  review: { icon: ICONS.eye, ring: 'bg-indigo-50 text-indigo-700 ring-indigo-100', label: 'Reviewing' },
  notice: { icon: ICONS2.note, ring: 'bg-accent-50 text-accent-700 ring-accent-100', label: 'Notice' },
  done: { icon: ICONS.check, ring: 'bg-emerald-500 text-white ring-emerald-200', label: 'Done' },
}

const RISK = {
  high: { label: 'High risk', cls: 'bg-red-600 text-white' },
  medium: { label: 'Medium risk', cls: 'bg-saffron-500 text-white' },
  low: { label: 'Low risk', cls: 'bg-emerald-100 text-emerald-800' },
  none: { label: 'No risk found', cls: 'bg-emerald-600 text-white' },
} as const

function download(name: string, text: string, mime: string) {
  const u = URL.createObjectURL(new Blob([text], { type: mime }))
  const a = document.createElement('a')
  a.href = u
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(u), 1000)
}

function Node({ e, last }: { e: armor.AgentEvent; last: boolean }) {
  const st = STEP[e.step ?? 'scan']
  const f = e.finding
  return (
    <li className="fade-up relative flex gap-3 pb-5 last:pb-0">
      {!last && <span aria-hidden="true" className="absolute left-[19px] top-10 h-[calc(100%-2.5rem)] w-0.5 bg-slate-200" />}
      <span className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full ring-4 ${st.ring}`}>
        <Icon d={st.icon} className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1 pt-1.5">
        {f ? (
          <div className="rounded-2xl border border-red-100 bg-red-50/60 p-3">
            <p className="text-sm font-semibold text-slate-900">{e.say}</p>
            <div className="mt-3 flex gap-3">
              <img src={f.thumb_url} alt="Exposed ID with private parts blacked out" className="h-20 w-28 shrink-0 rounded-xl object-cover ring-1 ring-red-100" />
              <div className="min-w-0">
                <ul className="flex flex-wrap gap-1.5">
                  {f.kinds.map((k) => <li key={k} className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-red-700 ring-1 ring-red-100">{k}</li>)}
                </ul>
                {f.masked.length > 0 && <p className="mt-2 break-all font-mono text-xs text-slate-600">{f.masked.join('  ')}</p>}
              </div>
            </div>
          </div>
        ) : e.step === 'lock' ? (
          <div className="rounded-2xl bg-saffron-50 p-3 ring-1 ring-saffron-100">
            <p className="text-sm font-bold text-saffron-700">Your turn: enter the OTP on UIDAI</p>
            <p className="mt-1 text-sm text-slate-700">{e.say}</p>
          </div>
        ) : (
          <p className={`text-sm ${e.step === 'done' ? 'font-bold text-slate-900' : 'text-slate-700'}`}>{e.say}</p>
        )}
      </div>
    </li>
  )
}

function Final({ done, notice }: { done: armor.AgentDone; notice?: string }) {
  const risk = done.risk ? RISK[done.risk] : null
  const n = done.exposed_count
  return (
    <section className={`${card} fade-up space-y-4`} aria-label="Summary">
      {done.error ? (
        <p className="text-sm text-red-700">We couldn&rsquo;t finish this scan. Please try again.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {risk && <span className={`rounded-full px-3.5 py-1.5 text-sm font-bold ${risk.cls}`}>{risk.label}</span>}
            {n !== undefined && (
              <p className="text-lg font-extrabold tracking-tight text-slate-900">
                {n === 0 ? 'No exposed copies found' : `${n} exposed ${n === 1 ? 'copy' : 'copies'} found`}
              </p>
            )}
          </div>
          {!risk && done.summary && <p className="text-sm text-slate-700">{done.summary}</p>}
        </>
      )}
      {notice && (
        <div>
          <h3 className="text-sm font-bold text-slate-900">Takedown notice</h3>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-2xl bg-slate-50 p-4 font-sans text-sm leading-relaxed text-slate-700 ring-1 ring-slate-100">{notice}</pre>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-xl ring-1 ring-slate-200">
              <span className="pl-3 text-sm font-semibold text-slate-700">Copy</span><CopyButton text={notice} label="takedown notice" />
            </span>
            <button type="button" onClick={() => download('takedown-notice.md', notice, 'text/markdown')} className={`${btnSecondary} !min-h-10 !px-4 !text-sm`}>
              <Icon d={ICONS.download} className="h-4 w-4" />.md
            </button>
            <button type="button" onClick={() => download('takedown-notice.txt', notice, 'text/plain')} className={`${btnSecondary} !min-h-10 !px-4 !text-sm`}>
              <Icon d={ICONS.download} className="h-4 w-4" />.txt
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-500">This is a draft. Please read it before you send it.</p>
        </div>
      )}
    </section>
  )
}

/** Leak alerts: plain story of what the agents did, from SSE events with `say`. */
export default function AgentsTab() {
  const [events, setEvents] = useState<armor.AgentEvent[]>([])
  const [running, setRunning] = useState(false)
  const [kind, setKind] = useState<'audit' | 'forgery' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [log, setLog] = useState(false)
  const stop = useRef<(() => void) | null>(null)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => () => stop.current?.(), [])

  const start = (params: Parameters<typeof armor.runAgents>[0]) => {
    stop.current?.()
    setEvents([])
    setError(null)
    setRunning(true)
    setKind(params.case)
    stop.current = armor.runAgents(
      params,
      (e) => {
        setEvents((xs) => [...xs, e])
        if (e.type === 'done') setRunning(false)
      },
      (m) => { void m; setError('The connection dropped before we finished. Please try again.'); setRunning(false) },
    )
  }

  const story = events.filter((e) => e.say)
  const doneEv = events.find((e) => e.type === 'done')
  const done = doneEv?.result as armor.AgentDone | undefined
  const last = armor.lastAttack

  useEffect(() => {
    if (running && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [story.length, running])

  return (
    <div className="space-y-5">
      <div className="fade-up text-center">
        <span className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-saffron-100 text-saffron-700"><Icon d={ICONS2.bell} className="h-8 w-8" /></span>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Leak alerts</h1>
        <p className="mx-auto mt-2 max-w-md text-[15px] leading-relaxed text-slate-600">
          We scan websites where your ID might be exposed, help lock your biometrics, and draft a takedown notice.
        </p>
      </div>

      <section className={`${card} space-y-3`}>
        <button type="button" disabled={running} onClick={() => start({ case: 'audit' })} className={`${btnPrimary} min-h-14 w-full text-base`}>
          <Icon d={ICONS2.scan} className="h-5 w-5" />{running && kind === 'audit' ? 'Scanning…' : 'Scan a demo hotel website'}
        </button>
        <button type="button" disabled={running || !last} onClick={() => last && start({ case: 'forgery', attack_id: last.id })} className={`${btnSecondary} w-full`}>
          Explain the last tampered copy
        </button>
        {!last && <p className="text-center text-xs text-slate-500">To try this, tamper with a copy first (open &ldquo;How do we know it&rsquo;s safe?&rdquo; on a result).</p>}
      </section>

      {error && <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

      {story.length > 0 && (
        <section className={card} aria-label="What happened">
          <ol aria-live="polite">
            {story.map((e, i) => <Node key={i} e={e} last={i === story.length - 1 && !running} />)}
          </ol>
          {running && (
            <p className="mt-3 flex items-center gap-2 pl-1 text-sm text-slate-500" role="status">
              <span className="spin-slow h-4 w-4 rounded-full border-2 border-accent-600 border-t-transparent" />Working on it…
            </p>
          )}
          <div ref={end} />
        </section>
      )}

      {done && <Final done={done} notice={kind === 'audit' ? done.notice : undefined} />}

      {events.length > 0 && (
        <div>
          <button type="button" onClick={() => setLog((v) => !v)} aria-expanded={log} className="mx-auto flex min-h-11 items-center gap-1 text-sm font-medium text-slate-500 hover:text-slate-800">
            {log ? 'Hide agent log' : 'Show agent log'}
          </button>
          {log && (
            <ul className="mt-2 space-y-1 rounded-2xl bg-slate-900 p-4 font-mono text-xs text-slate-300">
              {events.map((e, i) => (
                <li key={i} className="break-words"><span className="text-saffron-500">{e.agent}</span> <span className="text-slate-500">{e.type}</span> {e.tool ?? e.text ?? e.say ?? ''}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="px-2 text-center text-xs text-slate-500">
        Agents can only add protection or flag something for review. They never decide that something is safe.
      </p>
    </div>
  )
}
