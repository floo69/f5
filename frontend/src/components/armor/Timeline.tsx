import type { Step } from '../../armorApi'
import { ICONS } from '../helpers'
import { Icon } from '../ui'
import { card } from './styles'

const GROUPS: { label: string; keys: string[] }[] = [
  { label: 'Cleaning up photo', keys: ['capture', 'preprocess'] },
  { label: 'Finding private details', keys: ['detect', 'decide'] },
  { label: 'Hiding them for good', keys: ['destroy'] },
  { label: 'Adding purpose watermark', keys: ['watermark'] },
  { label: 'Double-checking', keys: ['verify'] },
  { label: 'Sealing', keys: ['seal'] },
]
type St = 'pending' | 'running' | 'done' | 'failed'

function groupStatus(steps: Step[], keys: string[]): St {
  const mine = steps.filter((s) => keys.includes(s.key))
  if (mine.length === 0) return 'pending'
  if (mine.some((s) => s.status === 'failed')) return 'failed'
  if (mine.every((s) => s.status === 'done')) return 'done'
  if (mine.some((s) => s.status === 'running' || s.status === 'done')) return 'running'
  return 'pending'
}

/** Calm progress with plain step names mapped from the backend step keys. */
export default function Timeline({ steps }: { steps: Step[] }) {
  const sts = GROUPS.map((g) => groupStatus(steps, g.keys))
  const doneN = sts.filter((s) => s === 'done').length
  const current = sts.findIndex((s) => s === 'running') >= 0 ? sts.findIndex((s) => s === 'running') : sts.findIndex((s) => s === 'pending')
  const pct = Math.round(((doneN + (current >= 0 ? 0.4 : 0)) / GROUPS.length) * 100)
  const R = 44
  const C = 2 * Math.PI * R
  return (
    <section className={`${card} fade-up text-center`} aria-label="Protecting your ID">
      <div className="relative mx-auto h-32 w-32">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
          <circle cx="50" cy="50" r={R} fill="none" stroke="#e2e8f0" strokeWidth="7" />
          <circle cx="50" cy="50" r={R} fill="none" stroke="url(#g)" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={C} strokeDashoffset={C * (1 - Math.min(pct, 100) / 100)} style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
          <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#0d9488" /><stop offset="1" stopColor="#f59e0b" /></linearGradient></defs>
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-accent-700">
          <Icon d={ICONS.shield} className="h-12 w-12" />
        </div>
      </div>
      <h2 className="mt-5 text-xl font-extrabold tracking-tight text-slate-900">Protecting your ID…</h2>
      <p className="mt-1 text-sm text-slate-600">This takes a few seconds. Everything happens on your device.</p>
      <ol className="mx-auto mt-6 max-w-xs space-y-3 text-left" role="status" aria-live="polite">
        {GROUPS.map((g, i) => {
          const s = sts[i]
          return (
            <li key={g.label} className="flex items-center gap-3">
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300 ${
                s === 'done' ? 'border-accent-600 bg-accent-600 text-white' : s === 'running' ? 'border-accent-600 bg-accent-50' : s === 'failed' ? 'border-red-500 bg-red-500 text-white' : 'border-slate-200 bg-white'
              }`}>
                {s === 'done' && <Icon d={ICONS.check} className="h-4 w-4" />}
                {s === 'running' && <span className="spin-slow h-3.5 w-3.5 rounded-full border-2 border-accent-600 border-t-transparent" />}
              </span>
              <span className={`text-[15px] ${s === 'pending' ? 'text-slate-400' : s === 'running' ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>{g.label}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
