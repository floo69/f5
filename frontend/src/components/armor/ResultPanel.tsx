import { useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS, ICONS2 } from '../helpers'
import { Icon } from '../ui'
import Inspector from './Inspector'
import { btnBase, btnGhost, btnPrimary, btnSecondary, card, fmtDate, fmtDay } from './styles'

const TIPS: [string, string][] = [
  ['Good light', ICONS2.sparkle],
  ['Fill the frame', ICONS2.scan],
  ['No glare or shadows', ICONS.eye],
  ['Original photo, not a screenshot', ICONS.camera],
]

type Chip = { label: string; icon: string; tone: 'hidden' | 'kept' }

/** Friendly chips from the findings (deduplicated). */
function chipsFor(findings: armor.IdFinding[]): Chip[] {
  const out = new Map<string, Chip>()
  const add = (c: Chip) => out.set(c.label, c)
  for (const f of findings) {
    const hide = f.action !== 'KEEP'
    switch (f.type) {
      case 'AADHAAR':
      case 'VID':
        add({ label: f.action === 'MASK_PARTIAL' ? 'Aadhaar number — last 4 kept' : 'Aadhaar number — hidden', icon: ICONS2.user, tone: 'hidden' })
        break
      case 'MASKED_AADHAAR':
        add({ label: 'Aadhaar number — already hidden', icon: ICONS2.user, tone: 'hidden' })
        break
      case 'PAN':
        add({ label: hide ? 'PAN number — hidden' : 'PAN number — kept', icon: ICONS2.note, tone: hide ? 'hidden' : 'kept' })
        break
      case 'QR':
      case 'BARCODE':
        add({ label: hide ? 'QR code — hidden' : 'QR code — kept', icon: ICONS2.qr, tone: hide ? 'hidden' : 'kept' })
        break
      case 'FINGERPRINT':
        add({ label: 'Thumbprint — removed', icon: ICONS2.hand, tone: 'hidden' })
        break
      case 'USER':
        add({ label: f.label ? `${f.label} — hidden (you chose)` : 'Your box — hidden', icon: ICONS.eye, tone: 'hidden' })
        break
      case 'FACE':
        add({ label: 'Photo — kept', icon: ICONS2.user, tone: 'kept' })
        break
      case 'DOB':
        add({ label: hide ? 'Date of birth — hidden' : 'Date of birth — kept', icon: ICONS2.clock, tone: hide ? 'hidden' : 'kept' })
        break
      case 'ADDRESS':
        add({ label: hide ? 'Address — hidden' : 'Address — kept', icon: ICONS2.home, tone: hide ? 'hidden' : 'kept' })
        break
      default:
        add({ label: hide ? 'Other numbers — hidden' : 'Other details — kept', icon: ICONS2.note, tone: hide ? 'hidden' : 'kept' })
    }
  }
  return [...out.values()]
}

function ArmoredView({ id }: { id: string }) {
  return (
    <div>
      <div className="relative select-none overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 shadow-inner">
        <img
          src={armor.viewUrl(id, 'after')}
          alt="Watermarked and redacted safe copy"
          className="block h-auto w-full"
          draggable={false}
        />
        <span className="absolute right-3 top-3 rounded-full bg-accent-700/90 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm">
          Watermarked &amp; Redacted
        </span>
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-4 py-2 text-sm"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-900">{v}</dd></div>
}

export default function ResultPanel({ result, jobId, onPurpose, onEdit, onRetake, onReset }: {
  result: armor.ArmorResult
  /** backend job id: every file/inspect/attack route is keyed by it (not the armor id) */
  jobId: string
  onPurpose: () => void
  onEdit: () => void
  onRetake: () => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const returnFocus = useRef<HTMLButtonElement>(null)
  const ok = result.decision === 'ARMOR_AND_ISSUE'
  const pp = result.preprocess
  const dl = (kind: armor.DownloadKind) => armor.downloadUrl(jobId, kind, result)
  const pdfUrl = dl('armored.pdf')
  const chips = chipsFor(result.findings)

  const share = async () => {
    setMsg(null)
    try {
      const url = dl('armored.png')
      if (!url) return
      const blob = await (await fetch(url)).blob()
      const file = new File([blob], 'safe-copy.png', { type: 'image/png' })
      if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: 'My safe ID copy' })
      else setMsg('Sharing isn’t available here. Please use Download instead.')
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) setMsg('We couldn’t open sharing. Please use Download instead.')
    }
  }

  const shareText = `Safe copy of my ID for ${result.recipient}: ${result.preset.label} only, valid till ${fmtDay(result.expires_at)}. Copy ID ${result.armor_id}. It is locked to this purpose and can be verified on SurakshitID.`

  // One tap: where the browser can share files (phones) the share sheet opens with the safe
  // copy attached and the user picks WhatsApp. wa.me cannot attach files, so on desktop we
  // download the copy and open WhatsApp with the message ready to send along with it.
  const whatsapp = async () => {
    setMsg(null)
    const url = dl('armored.png')
    if (!url) return
    try {
      const blob = await (await fetch(url)).blob()
      const file = new File([blob], `safe-copy-${result.armor_id}.png`, { type: 'image/png' })
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], text: shareText })
        return
      }
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = file.name
      a.click()
      window.setTimeout(() => URL.revokeObjectURL(a.href), 10000)
      window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, '_blank', 'noopener')
      setMsg('Your safe copy was saved. In WhatsApp, choose a chat and attach it with the paperclip.')
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError')) setMsg('We couldn’t open WhatsApp. Please use Download instead.')
    }
  }

  return (
    <div className="space-y-4 fade-up">
      {ok && (
        <div role="status" className="flex items-center gap-4 rounded-3xl bg-gradient-to-br from-emerald-500 to-accent-700 p-5 text-white shadow-lg">
          <span className="pop flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-white/20"><Icon d={ICONS.check} className="h-8 w-8" /></span>
          <div className="min-w-0">
            <h2 className="text-2xl font-extrabold leading-tight tracking-tight">Your safe copy is ready</h2>
            <p className="mt-0.5 text-sm text-white/90">For {result.recipient}, valid till {fmtDay(result.expires_at)}.</p>
          </div>
        </div>
      )}
      {result.decision === 'INSUFFICIENT_PURPOSE' && (
        <div role="status" className="rounded-3xl bg-saffron-50 p-5 ring-1 ring-saffron-100">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-saffron-500 text-white"><Icon d={ICONS.alert} className="h-6 w-6" /></span>
            <h2 className="text-xl font-extrabold tracking-tight text-slate-900">Tell us who it&rsquo;s for</h2>
          </div>
          <p className="mt-3 text-sm text-slate-700">We need to know who will get this copy and for how long, so it can be locked to them.</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">{result.reasons.map((r) => <li key={r}>&bull; {r}</li>)}</ul>
          <button type="button" onClick={onPurpose} className={`${btnPrimary} mt-4 w-full`}>Add details</button>
        </div>
      )}
      {result.decision === 'BLOCK_FOR_REVIEW' && (
        <div role="status" className="rounded-3xl bg-red-50 p-5 ring-1 ring-red-100">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-red-500 text-white"><Icon d={ICONS.eye} className="h-6 w-6" /></span>
            <h2 className="text-xl font-extrabold tracking-tight text-slate-900">We couldn&rsquo;t read this photo clearly</h2>
          </div>
          <p className="mt-3 text-sm text-slate-700">To keep you safe, we didn&rsquo;t make a copy. A fresh photo usually fixes it. Try this:</p>
          <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {TIPS.map(([t, d]) => (
              <li key={t} className="flex items-center gap-2.5 rounded-2xl bg-white px-3 py-2.5 text-sm font-medium text-slate-800 ring-1 ring-red-100">
                <Icon d={d} className="h-5 w-5 shrink-0 text-red-500" />{t}
              </li>
            ))}
          </ul>
          <button type="button" onClick={onRetake} className={`${btnPrimary} mt-4 w-full`}>Try another photo</button>
        </div>
      )}

      {ok && result.careful && (
        <p className="flex items-start gap-2.5 rounded-2xl bg-saffron-50 px-4 py-3 text-sm text-saffron-700 ring-1 ring-saffron-100" role="note">
          <Icon d={ICONS2.info} className="mt-0.5 h-5 w-5 shrink-0" />
          Some text was hard to read, so we hid a little extra to keep you safe.
        </p>
      )}

      {ok && (
        <section className={card} aria-label="Watermarked and redacted copy">
          <ArmoredView id={jobId} />
          {chips.length > 0 && (
            <ul className="mt-4 flex flex-wrap gap-2" aria-label="What we did">
              {chips.map((c) => (
                <li key={c.label} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${
                  c.tone === 'hidden' ? 'bg-accent-50 text-accent-800 ring-accent-100' : 'bg-slate-50 text-slate-700 ring-slate-200'
                }`}>
                  <Icon d={c.icon} className="h-3.5 w-3.5" />{c.label}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {ok && (
        <section className={`${card} space-y-3`} aria-label="Save your copy">
          <a href={dl('armored.png') ?? undefined} download="safe-copy.png" className={`${btnPrimary} min-h-14 w-full text-base`}>
            <Icon d={ICONS.download} className="h-5 w-5" />Download safe copy
          </a>
          <button type="button" onClick={() => void whatsapp()}
            className={`${btnBase} min-h-14 w-full bg-[#25D366] text-base text-white shadow-sm hover:bg-[#1ebe5b]`}>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 00-8.6 15.100L2 22l5-1.300A10 10 0 1012 2zm5.800 14.200c-.2.700-1.300 1.300-1.800 1.300-.5.100-1 .200-3.300-.700-2.800-1.100-4.600-3.900-4.700-4.100-.1-.2-1.100-1.500-1.100-2.800s.7-2 1-2.300c.2-.3.500-.3.700-.3h.5c.2 0 .4 0 .6.500l.8 2c.1.200.1.300 0 .500l-.3.400-.4.500c-.1.100-.3.300-.1.600.2.300.8 1.300 1.700 2.100 1.200 1 2.100 1.300 2.400 1.500.3.100.5.100.600-.1l.9-1.100c.2-.3.400-.2.600-.1l1.900.9c.3.100.5.200.5.300.100.100.100.700-.1 1.200z" />
            </svg>
            Share on WhatsApp
          </button>
          <div className="grid grid-cols-2 gap-3">
            {pdfUrl ? (
              <a href={pdfUrl} download="safe-copy.pdf" className={btnSecondary}>PDF</a>
            ) : (
              <span aria-disabled="true" className={`${btnSecondary} opacity-50`} title="PDF is available with the local service">PDF</span>
            )}
            {typeof navigator.share === 'function' ? (
              <button type="button" onClick={() => void share()} className={btnSecondary}><Icon d={ICONS.share} className="h-5 w-5" />Share</button>
            ) : (
              <span aria-disabled="true" className={`${btnSecondary} opacity-50`}>Share</span>
            )}
          </div>
          {msg && <p role="alert" className="text-sm text-saffron-700">{msg}</p>}
          <p className="break-words rounded-2xl bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
            <span className="font-semibold text-slate-700">Stamped on your copy: </span>{result.watermark_text}
          </p>
        </section>
      )}

      {ok && (
        <div className="space-y-2">
          <button type="button" onClick={onEdit} className="mx-auto flex min-h-11 items-center gap-1.5 text-sm font-semibold text-accent-800 underline-offset-4 hover:underline">
            <Icon d={ICONS.eye} className="h-4 w-4" />Hide something else
          </button>
          <button ref={returnFocus} type="button" onClick={() => setOpen(true)} className="mx-auto flex min-h-11 items-center gap-1.5 text-sm font-semibold text-accent-800 underline-offset-4 hover:underline">
            <Icon d={ICONS2.info} className="h-4 w-4" />How do we know it&rsquo;s safe?
          </button>
          <details className="group rounded-2xl border border-slate-200/70 bg-white/70">
            <summary className="flex min-h-12 cursor-pointer items-center justify-between px-4 text-sm font-semibold text-slate-700">
              Technical details
              <Icon d={ICONS2.chevron} className="h-4 w-4 transition-transform group-open:rotate-180" />
            </summary>
            <dl className="divide-y divide-slate-100 px-4 pb-2">
              <Row k="Hidden data removed from photo" v={`${pp.metadata_removed.length} items`} />
              <Row k="Sharpness" v={`${Math.round(pp.blur_score)}${pp.blur_ok ? '' : ' (low)'}`} />
              <Row k="Decision time" v={`${(result.decision_us / 1000).toFixed(2)} ms`} />
              {result.badge && <Row k="Copy ID" v={<span className="font-mono">{result.badge.armor_id}</span>} />}
              <Row k="Issued" v={fmtDate(result.issued_at)} />
            </dl>
          </details>
        </div>
      )}

      {result.decision === 'BLOCK_FOR_REVIEW' && (
        <details className="group rounded-2xl border border-slate-200/70 bg-white/70">
          <summary className="flex min-h-12 cursor-pointer items-center justify-between px-4 text-sm font-semibold text-slate-700">
            Technical details
            <Icon d={ICONS2.chevron} className="h-4 w-4 transition-transform group-open:rotate-180" />
          </summary>
          <dl className="divide-y divide-slate-100 px-4 pb-2">
            <Row k="Sharpness" v={`${Math.round(pp.blur_score)}${pp.blur_ok ? '' : ' (too low)'}`} />
            <Row k="Decision time" v={`${(result.decision_us / 1000).toFixed(2)} ms`} />
          </dl>
        </details>
      )}

      <div className="flex justify-center pt-1">
        <button type="button" onClick={onReset} className={btnGhost}><Icon d={ICONS.refresh} className="h-5 w-5" />Protect another ID</button>
      </div>
      {open && <Inspector id={jobId} onClose={() => { setOpen(false); returnFocus.current?.focus() }} />}
    </div>
  )
}
