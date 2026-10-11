import type { Job } from '../api'

export default function ProgressCard({ job, filename }: { job: Job | null; filename: string }) {
  const done = job?.progress.pages_done ?? 0
  const total = job?.progress.pages_total ?? 0
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const text =
    !job || job.status === 'queued'
      ? 'Queued…'
      : total > 0
        ? `Scanning page ${Math.min(done + 1, total)} of ${total}…`
        : 'Processing…'
  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-8">
      <h2 className="text-lg font-semibold text-slate-900">Processing {filename}</h2>
      <p className="mt-1 text-sm text-slate-500" role="status">
        {text}
      </p>
      <div
        className="mt-5 h-2.5 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div className="h-full rounded-full bg-accent-600 transition-all duration-300" style={{ width: `${Math.max(pct, 4)}%` }} />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {done} / {total || '?'} pages · detect → redact → verify, all on this machine
      </p>
    </section>
  )
}
