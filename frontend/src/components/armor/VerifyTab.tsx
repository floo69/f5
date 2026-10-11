import { useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS, ICONS2 } from '../helpers'
import { Icon } from '../ui'
import { RegionOverlay, VerdictCard } from './ForgeryView'
import { btnPrimary, btnSecondary, card, friendlyError } from './styles'

export default function VerifyTab() {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<armor.VerifyReport | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [isPdf, setIsPdf] = useState(false)

  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])

  const run = async (f: File) => {
    setBusy(true)
    setError(null)
    setReport(null)
    setIsPdf(f.type === 'application/pdf')
    setUrl(URL.createObjectURL(f)) // the already-protected file chosen by the person checking it
    try {
      setReport(await armor.verifyFile(f))
    } catch (e) {
      setError(friendlyError(e, 'We couldn’t check this file. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  const forged = report?.status === 'FORGERY_DETECTED'

  return (
    <div className="space-y-5">
      <div className="fade-up text-center">
        <span className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-accent-100 text-accent-800"><Icon d={ICONS2.scan} className="h-8 w-8" /></span>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Check a copy</h1>
        <p className="mx-auto mt-2 max-w-md text-[15px] text-slate-600">
          Got an ID copy from a customer or guest? See in a few seconds if it&rsquo;s genuine, still valid and untouched.
        </p>
      </div>
      <section className={card}>
        <button type="button" disabled={busy} onClick={() => input.current?.click()} className={`${report ? btnSecondary : btnPrimary} min-h-14 w-full text-base`}>
          <Icon d={ICONS.upload} className="h-5 w-5" />{busy ? 'Checking…' : report ? 'Check another copy' : 'Choose the copy to check'}
        </button>
        <input ref={input} type="file" accept="image/png,application/pdf" className="sr-only" aria-label="Choose the copy to check"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(f); e.target.value = '' }} />
        <p className="mt-3 text-center text-xs text-slate-500">PNG or PDF. The file stays on this device.</p>
        {error && <p role="alert" className="mt-3 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
      </section>

      {report && url && (
        <section className="space-y-4" aria-label="Result">
          <VerdictCard report={report} flashKey={url} />
          {forged && (
            <div className="space-y-2">
              {isPdf ? (
                <p className="text-sm text-slate-600">The edited areas can&rsquo;t be drawn on a PDF preview.</p>
              ) : (
                <>
                  <RegionOverlay src={url} report={report} alt="The copy you chose, with the edited areas marked in red" />
                  <p className="text-center text-xs text-slate-500">Red boxes show where the picture was changed.</p>
                </>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
