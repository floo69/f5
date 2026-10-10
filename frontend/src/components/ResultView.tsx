import { useState } from 'react'
import type { Result } from '../api'
import PageImage from './PageImage'
import PageViewer from './PageViewer'
import SummaryBar from './SummaryBar'
import { DECISION_META } from './helpers'

export default function ResultView({ result, mock, onReset }: { result: Result; mock: boolean; onReset: () => void }) {
  const [sel, setSel] = useState(0)
  const page = result.pages[Math.min(sel, result.pages.length - 1)]

  return (
    <div className="space-y-6">
      <SummaryBar result={result} mock={mock} onReset={onReset} />
      <nav aria-label="Pages" className="flex gap-3 overflow-x-auto pb-1">
        {result.pages.map((p) => {
          const m = DECISION_META[p.decision]
          const active = p.page === page.page
          return (
            <button key={p.page} type="button" onClick={() => setSel(p.page)} aria-current={active ? 'page' : undefined}
              aria-label={`Page ${p.page + 1}, ${m.label}`}
              className={`w-28 shrink-0 rounded-xl border bg-white p-2 text-left shadow-sm transition ${
                active ? 'border-accent-600 ring-2 ring-accent-600/30' : 'border-slate-200 hover:border-slate-400'
              }`}>
              <PageImage jobId={result.doc_id} page={p} view="after" boxes={false} mock={mock} dpi={40} interactive={false} />
              <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-slate-700">
                <span className={`h-2.5 w-2.5 rounded-full ${m.dot}`} />Page {p.page + 1}
              </div>
            </button>
          )
        })}
      </nav>
      <PageViewer key={page.page} jobId={result.doc_id} page={page} mock={mock} />
    </div>
  )
}
