import { useState } from 'react'
import type { PageResult } from '../api'
import PageImage from './PageImage'
import { countChips, DECISION_META } from './helpers'

const STAGES: [string, string][] = [
  ['render', 'Render'],
  ['text', 'Text layer'],
  ['aadhaar', 'Aadhaar'],
  ['fingerprint', 'Fingerprint'],
]

export default function PageViewer({ jobId, page, mock }: { jobId: string; page: PageResult; mock: boolean }) {
  const [boxes, setBoxes] = useState(true)
  const meta = DECISION_META[page.decision]
  const chips = countChips(page.counts)
  const max = Math.max(1, ...STAGES.map(([k]) => page.timings_ms[k] ?? 0))

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-label={`Page ${page.page + 1} detail`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="mr-2 text-base font-semibold text-slate-900">Page {page.page + 1}</h3>
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${meta.chip}`}>{meta.label}</span>
          {chips.length === 0 && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">No findings</span>}
          {chips.map((c) => (
            <span key={c} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">{c}</span>
          ))}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={boxes} onChange={(e) => setBoxes(e.target.checked)}
            className="h-4 w-4 accent-teal-700" />
          Show finding boxes
        </label>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-6 sm:grid-cols-2">
        {(['before', 'after'] as const).map((v) => (
          <figure key={v}>
            <figcaption className="mb-2 text-sm font-medium text-slate-700">
              {v === 'before' ? 'Original (thumbprints pixelated for display)' : 'After redaction'}
            </figcaption>
            <div className="mx-auto max-w-[420px]">
              <PageImage jobId={jobId} page={page} view={v} boxes={boxes} mock={mock} />
            </div>
          </figure>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 border-t sm:grid-cols-2 border-slate-100 pt-5">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Decision</h4>
          <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
            {page.reasons.map((r) => (
              <li key={r} className="flex gap-2"><span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dot}`} />{r}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            {page.text_layer ? 'Text layer present' : `Scanned page · OCR quality ${page.ocr_quality.toFixed(2)}`}
          </p>
        </div>
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Stage timings</h4>
          <ul className="mt-2 space-y-1.5">
            {STAGES.map(([k, name]) => {
              const v = page.timings_ms[k] ?? 0
              return (
                <li key={k} className="flex items-center gap-3 text-xs text-slate-600">
                  <span className="w-20">{name}</span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <span className="block h-full rounded-full bg-accent-600/70" style={{ width: `${(v / max) * 100}%` }} />
                  </span>
                  <span className="w-16 text-right tabular-nums">{v.toFixed(1)} ms</span>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </section>
  )
}
