import { fileUrl, type Result } from '../api'
import { ICONS, plural, shortHash, totals } from './helpers'
import { CopyButton, Icon } from './ui'

export default function SummaryBar({ result, onReset, mock }: { result: Result; onReset: () => void; mock: boolean }) {
  const clean = result.status === 'VERIFIED_CLEAN' && result.verification.status === 'pass'
  const t = totals(result.pages)
  const blockedPages = result.pages.filter((p) => p.decision === 'BLOCK_FOR_REVIEW')
  const id = result.doc_id
  const dl = 'inline-flex min-h-11 items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium shadow-sm'
  const dlDisabled = mock ? ' (demo)' : ''

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6" aria-label="Result summary">
      <div className="flex flex-col items-start justify-between gap-4 lg:flex-row lg:gap-6">
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:gap-4">
          <div className={`flex h-12 w-12 shrink-0 sm:h-16 sm:w-16 items-center justify-center rounded-2xl text-white ${clean ? 'bg-emerald-600' : 'bg-red-600'}`}>
            <Icon d={clean ? ICONS.check : ICONS.alert} className="h-9 w-9" />
          </div>
          <div>
            <h2 className={`text-2xl font-semibold tracking-tight ${clean ? 'text-emerald-700' : 'text-red-700'}`}>
              {clean ? 'Verified clean' : 'Blocked for review'}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {clean
                ? 'Re-scan of the redacted PDF found no thumb impressions or Aadhaar numbers.'
                : 'Do not publish this document until a person has reviewed it.'}
            </p>
            {!clean && (
              <ul className="mt-2 space-y-1 text-sm text-red-800">
                {result.verification.status === 'fail' &&
                  result.verification.problems.map((p, i) => (
                    <li key={i}>• Verification failed on page {p.page + 1} ({p.type}): {p.detail}</li>
                  ))}
                {blockedPages.map((p) => (
                  <li key={p.page}>• Page {p.page + 1}: {p.reasons[0] ?? 'blocked'}</li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <a href={fileUrl(id, 'redacted')} className={`${dl} bg-accent-700 text-white hover:bg-accent-800`}>
            <Icon d={ICONS.download} className="h-4 w-4" />Redacted PDF{dlDisabled}
          </a>
          <a href={fileUrl(id, 'certificate.pdf')} className={`${dl} border border-slate-300 bg-white text-slate-800 hover:bg-slate-50`}>
            <Icon d={ICONS.download} className="h-4 w-4" />Certificate{dlDisabled}
          </a>
          <a href={fileUrl(id, 'certificate')} target="_blank" rel="noreferrer"
            className={`${dl} px-2 text-slate-600 hover:text-slate-900`}>JSON</a>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 items-end gap-4 sm:gap-6 md:grid-cols-[1fr_auto] border-t border-slate-100 pt-5">
        <div>
          <p className="text-lg font-medium text-slate-900">
            {plural(t.FINGERPRINT, 'thumb impression')} · {t.AADHAAR + t.VID} Aadhaar/VID redacted · {t.MASKED_AADHAAR} masked (already compliant)
          </p>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1">
              sha256 in <code className="font-mono text-slate-700">{shortHash(result.sha256_in)}</code>
              <CopyButton text={result.sha256_in} label="input hash" />
            </span>
            <span className="inline-flex items-center gap-1">
              sha256 out <code className="font-mono text-slate-700">{shortHash(result.sha256_out)}</code>
              <CopyButton text={result.sha256_out} label="output hash" />
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:gap-5">
          <div className="text-right">
            <div className="text-2xl font-semibold tabular-nums text-slate-900">
              {((result.timings_ms.total ?? 0) / 1000).toFixed(2)} s
            </div>
            <div className="text-xs text-slate-500">total · {plural(result.page_count, 'page')}</div>
          </div>
          <button type="button" onClick={onReset}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50">
            <Icon d={ICONS.refresh} className="h-4 w-4" />Process another
          </button>
        </div>
      </div>
    </section>
  )
}
