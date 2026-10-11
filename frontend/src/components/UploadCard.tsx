import { useRef, useState } from 'react'
import type { Sample } from '../api'
import { ICONS } from './helpers'
import { Icon } from './ui'

interface Props {
  samples: Sample[]
  busy: boolean
  error: string | null
  onFile: (f: File) => void
  onSample: (name: string) => void
  onDemo?: () => void
}

export default function UploadCard({ samples, busy, error, onFile, onSample, onDemo }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  const take = (f: File | undefined) => {
    if (f) onFile(f)
  }

  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-8">
      <h2 className="text-lg font-semibold text-slate-900">Check a registration document</h2>
      <p className="mt-1 text-sm text-slate-500">
        Thumb impressions and Aadhaar numbers are detected and permanently removed from the PDF, then
        the result is re-scanned to verify nothing remains.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          take(e.dataTransfer.files[0])
        }}
        className={`mt-6 flex flex-col items-center rounded-xl border-2 border-dashed px-4 py-8 text-center sm:px-6 sm:py-12 transition-colors ${
          over ? 'border-accent-600 bg-accent-50' : 'border-slate-300 bg-slate-50'
        }`}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-accent-700 shadow-sm ring-1 ring-slate-200">
          <Icon d={ICONS.upload} className="h-6 w-6" />
        </div>
        <p className="mt-4 font-medium text-slate-800">Drag and drop a PDF here</p>
        <p className="mt-1 text-sm text-slate-500">or</p>
        <button
          type="button"
          disabled={busy}
          onClick={() => input.current?.click()}
          className="mt-3 min-h-11 rounded-lg bg-accent-700 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-accent-800 disabled:opacity-50"
        >
          Choose file
        </button>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Choose a PDF file"
          onChange={(e) => {
            take(e.target.files?.[0])
            e.target.value = ''
          }}
        />
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800 ring-1 ring-red-200">
          {error}
        </p>
      )}

      <div className="mt-8">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold text-slate-800">Or try a synthetic sample</h3>
          <span className="text-xs text-slate-500">All samples are synthetic</span>
        </div>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {samples.length === 0 && <li className="text-sm text-slate-400">No samples available.</li>}
          {samples.map((s) => (
            <li key={s.name}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onSample(s.name)}
                className="flex min-h-11 w-full items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm hover:border-accent-600 hover:bg-accent-50 disabled:opacity-50"
              >
                <Icon d={ICONS.file} className="h-5 w-5 shrink-0 text-slate-400" />
                <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{s.name}</span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {s.mode === 'scanned' ? 'scanned' : 'born-digital'}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {onDemo && (
          <button
            type="button"
            onClick={onDemo}
            className="mt-5 text-sm font-medium text-accent-700 underline-offset-2 hover:underline"
          >
            Load demo result
          </button>
        )}
      </div>
    </section>
  )
}
