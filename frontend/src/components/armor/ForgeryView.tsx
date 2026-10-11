import { useState } from 'react'
import type { VerifyReport } from '../../armorApi'
import { ICONS, ICONS2 } from '../helpers'
import { Icon } from '../ui'
import { fmtDay, fmtDate, prettyPurpose } from './styles'

/** Image with altered_regions drawn as red boxes (pixel coords -> % of the image size). */
export function RegionOverlay({ src, report, alt }: { src: string; report: VerifyReport; alt: string }) {
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null)
  const w = nat?.w ?? report.width
  const h = nat?.h ?? report.height
  return (
    <div className="relative w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
      <img
        src={src}
        alt={alt}
        className="block h-auto w-full"
        onLoad={(e) => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
      />
      {report.altered_regions.map((r, i) => (
        <div
          key={i}
          aria-hidden="true"
          className="absolute border-2 border-red-600 bg-red-500/20"
          style={{
            left: `${(r[0] / w) * 100}%`,
            top: `${(r[1] / h) * 100}%`,
            width: `${((r[2] - r[0]) / w) * 100}%`,
            height: `${((r[3] - r[1]) / h) * 100}%`,
          }}
        />
      ))}
    </div>
  )
}

type Tone = 'green' | 'red' | 'grey'
const TONE: Record<Tone, { box: string; dot: string }> = {
  green: { box: 'bg-gradient-to-br from-emerald-500 to-accent-700 text-white', dot: 'bg-white/20' },
  red: { box: 'bg-gradient-to-br from-red-500 to-red-700 text-white', dot: 'bg-white/20' },
  grey: { box: 'bg-slate-100 text-slate-800 ring-1 ring-slate-200', dot: 'bg-slate-200' },
}

function plain(r: VerifyReport): { tone: Tone; title: string; sub: string; icon: string } {
  const who = r.recipient ? `for ${r.recipient}` : ''
  const purpose = prettyPurpose(r.purpose)
  switch (r.status) {
    case 'AUTHENTIC':
      return {
        tone: 'green', icon: ICONS.check,
        title: 'Genuine copy',
        sub: [who, purpose, r.expires_at ? `valid till ${fmtDay(r.expires_at)}` : ''].filter(Boolean).join(' \u00b7 '),
      }
    case 'FORGERY_DETECTED':
      return { tone: 'red', icon: ICONS.alert, title: 'This copy was edited', sub: 'Parts of the picture don\u2019t match what was originally issued. Don\u2019t accept it.' }
    case 'EXPIRED':
      return { tone: 'grey', icon: ICONS2.clock, title: 'This copy has expired', sub: r.expires_at ? `It was only valid till ${fmtDay(r.expires_at)}. Ask the owner for a new one.` : 'Ask the owner for a new one.' }
    case 'REVOKED':
      return { tone: 'grey', icon: ICONS2.ban, title: 'The owner withdrew this copy', sub: 'It can no longer be used. Ask the owner for a new one.' }
    case 'UNKNOWN_BADGE':
      return { tone: 'grey', icon: ICONS2.info, title: 'We don\u2019t recognise this copy', sub: 'It was not issued by this app, so we can\u2019t vouch for it.' }
    default:
      return { tone: 'grey', icon: ICONS2.info, title: 'This isn\u2019t a SurakshitID copy', sub: 'We found no seal on it, so we can\u2019t tell if it is genuine.' }
  }
}

/** Plain verdict. `expert` adds the exact coordinates (Proof for experts drawer). `flashKey` re-triggers the one-shot flash. */
export function VerdictCard({ report, flashKey, expert = false }: { report: VerifyReport; flashKey?: string; expert?: boolean }) {
  const m = plain(report)
  const t = TONE[m.tone]
  const forged = report.status === 'FORGERY_DETECTED'
  return (
    <div role={forged ? 'alert' : 'status'} className="fade-up">
      <div key={flashKey} className={`flex items-center gap-4 rounded-3xl p-5 ${t.box}`}>
        <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${t.dot}`}><Icon d={m.icon} className="h-7 w-7" /></span>
        <div className="min-w-0">
          <p className="text-xl font-extrabold leading-tight tracking-tight sm:text-2xl">{m.title}</p>
          {m.sub && <p className={`mt-0.5 text-sm ${m.tone === 'grey' ? 'text-slate-600' : 'text-white/90'}`}>{m.sub}</p>}
        </div>
      </div>
      {expert && (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">Status</dt><dd className="font-mono text-xs font-medium">{report.status}</dd>
          {report.armor_id && <><dt className="text-slate-500">Copy ID</dt><dd className="font-mono text-xs font-medium break-all">{report.armor_id}</dd></>}
          <dt className="text-slate-500">Seal</dt>
          <dd className={`font-medium ${report.signature_ok ? 'text-emerald-700' : 'text-red-700'}`}>{report.signature_ok ? 'valid' : 'invalid'}</dd>
          {report.expires_at && <><dt className="text-slate-500">Expires</dt><dd className="font-medium">{fmtDate(report.expires_at)}</dd></>}
        </dl>
      )}
      {expert && report.altered_regions.length > 0 && (
        <div className="mt-3 rounded-2xl bg-red-50 p-3 ring-1 ring-red-100">
          <p className="text-sm font-semibold text-red-800">
            {report.altered_regions.length} altered region{report.altered_regions.length === 1 ? '' : 's'} &middot; {report.altered_tiles}/{report.total_tiles} tiles
          </p>
          <ul className="mt-1 space-y-0.5 font-mono text-xs text-red-900">
            {report.altered_regions.map((r, i) => (
              <li key={i}>[{r.join(', ')}] <span className="text-red-700">({r[2] - r[0]}&times;{r[3] - r[1]} px)</span></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
