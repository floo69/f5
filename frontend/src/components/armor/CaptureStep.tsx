import { useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS, ICONS2 } from '../helpers'
import { Icon } from '../ui'
import CameraCapture from './CameraCapture'
import { btnPrimary, btnSecondary, card, friendlyError } from './styles'

export interface Captured {
  file: File
  source: 'camera' | 'upload'
}

interface Props {
  active: boolean
  captured: Captured | null
  onCaptured: (c: Captured | null) => void
  onNext: () => void
}

const BENEFITS: [string, string][] = [
  ['Stays on your device', ICONS.lock],
  ["Can't be reused", ICONS2.ban],
  ['Edits are detected', ICONS.eye],
]

function Hero() {
  return (
    <div className="fade-up text-center">
      <div className="mx-auto mb-5 flex h-24 w-24 items-center justify-center rounded-[2rem] bg-gradient-to-br from-accent-600 to-accent-800 text-white shadow-[0_16px_32px_-12px_rgb(15_118_110/0.7)]">
        <svg viewBox="0 0 48 48" className="h-14 w-14" fill="none" aria-hidden="true">
          <rect x="6" y="12" width="36" height="24" rx="4" fill="#fff" fillOpacity=".18" stroke="#fff" strokeWidth="2" />
          <circle cx="16" cy="21" r="3.5" fill="#fff" />
          <path d="M11 31c.8-3 3-4.200 5-4.200s4.200 1.200 5 4.200" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
          <rect x="26" y="19" width="11" height="3" rx="1.500" fill="#fff" />
          <rect x="26" y="25" width="11" height="3" rx="1.500" fill="#f59e0b" />
        </svg>
      </div>
      <h1 className="text-[1.75rem] font-extrabold leading-tight tracking-tight text-slate-900 sm:text-4xl">
        Protect your ID <span className="text-accent-700">before you share it</span>
      </h1>
      <p className="mx-auto mt-3 max-w-md text-[15px] leading-relaxed text-slate-600">
        Get a safe copy of your Aadhaar or PAN that only works for one person and one reason.
      </p>
      <ul className="mt-4 flex flex-wrap justify-center gap-2">
        {BENEFITS.map(([t, d]) => (
          <li key={t} className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-medium text-accent-900 shadow-sm ring-1 ring-accent-100">
            <Icon d={d} className="h-3.5 w-3.5 text-accent-700" />{t}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function CaptureStep({ active, captured, onCaptured, onNext }: Props) {
  const upload = useRef<HTMLInputElement>(null)
  const phone = useRef<HTMLInputElement>(null)
  const [cam, setCam] = useState(false)
  const [samples, setSamples] = useState<armor.IdSample[]>([])
  const [thumbUrl, setThumb] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)

  useEffect(() => {
    void armor.listIdSamples().then(setSamples, () => setSamples([]))
  }, [])

  // Small preview of the chosen photo (samples are already pixelated; PDFs get an icon).
  useEffect(() => {
    if (!captured || !captured.file.type.startsWith('image/')) return
    const u = URL.createObjectURL(captured.file)
    setThumb(u)
    return () => URL.revokeObjectURL(u)
  }, [captured])

  const thumb = captured?.file.type.startsWith('image/') ? thumbUrl : null

  const take = (f: File | undefined, source: 'camera' | 'upload') => {
    if (f) {
      setError(null)
      onCaptured({ file: f, source })
    }
  }

  const sample = async (name: string) => {
    setLoading(name)
    setError(null)
    try {
      take(await armor.getIdSampleFile(name), 'upload')
    } catch (e) {
      setError(friendlyError(e, 'We could not load that sample. Please try another.'))
    } finally {
      setLoading(null)
    }
  }

  if (cam && active) {
    return (
      <section className={card} aria-label="Take a photo">
        <h2 className="mb-3 text-lg font-bold text-slate-900">Take a photo of your ID</h2>
        <CameraCapture
          onCancel={() => setCam(false)}
          onCapture={(b) => {
            setCam(false)
            take(new File([b], 'capture.jpg', { type: 'image/jpeg' }), 'camera')
          }}
        />
      </section>
    )
  }

  return (
    <div className="space-y-6">
      <Hero />
      <section className={`${card} fade-up space-y-4`} aria-label="Add a photo">
        {captured ? (
          <div className="flex items-center gap-4">
            {thumb ? (
              <img src={thumb} alt="Your chosen photo" className="h-16 w-24 shrink-0 rounded-xl object-cover ring-1 ring-slate-200" />
            ) : (
              <div className="flex h-16 w-24 shrink-0 items-center justify-center rounded-xl bg-slate-50 text-slate-400 ring-1 ring-slate-200">
                <Icon d={ICONS.file} className="h-7 w-7" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                <Icon d={ICONS.check} className="h-4 w-4 text-emerald-600" />Photo added
              </p>
              <p className="truncate text-xs text-slate-500">{captured.file.name}</p>
            </div>
            <button type="button" onClick={() => onCaptured(null)} className="min-h-11 rounded-xl px-3 text-sm font-medium text-slate-600 hover:bg-slate-100">
              Change
            </button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <button type="button" onClick={() => setCam(true)} className={`${btnPrimary} min-h-14 text-base`}>
              <Icon d={ICONS.camera} className="h-6 w-6" />Take photo
            </button>
            <button type="button" onClick={() => upload.current?.click()} className={`${btnSecondary} min-h-14 text-base`}>
              <Icon d={ICONS.upload} className="h-6 w-6" />Upload
            </button>
          </div>
        )}
        <input ref={upload} type="file" accept="image/*,application/pdf" className="sr-only" aria-label="Upload a photo or PDF of your ID"
          onChange={(e) => { take(e.target.files?.[0], 'upload'); e.target.value = '' }} />
        <input ref={phone} type="file" accept="image/*" capture="environment" className="sr-only" aria-label="Take a photo with the phone camera app"
          onChange={(e) => { take(e.target.files?.[0], 'camera'); e.target.value = '' }} />
        {!captured && (
          <button type="button" onClick={() => phone.current?.click()}
            className="min-h-11 w-full text-sm font-medium text-accent-700 underline-offset-2 hover:underline md:hidden">
            Camera not working? Use your phone&rsquo;s camera app
          </button>
        )}
        {error && <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

        {captured && (
          <button type="button" onClick={onNext} className={`${btnPrimary} w-full min-h-14 text-base`}>Continue</button>
        )}

        {!captured && samples.length > 0 && (
          <div className="border-t border-slate-100 pt-4">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
              <Icon d={ICONS2.sparkle} className="h-4 w-4 text-saffron-600" />Just exploring? Try a sample
            </p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {samples.map((s) => (
                <button key={s.name} type="button" disabled={loading !== null} onClick={() => void sample(s.name)}
                  className="min-h-11 rounded-full border border-saffron-100 bg-saffron-50 px-4 text-sm font-medium text-saffron-700 transition hover:border-saffron-500 disabled:opacity-50">
                  {loading === s.name ? 'Loading…' : s.label}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-500">Samples are made-up IDs. Nothing real is used.</p>
          </div>
        )}
      </section>
      <p className="px-2 text-center text-xs text-slate-500">
        Your photo is handled on this device and the local service. It is never sent to the internet.
      </p>
    </div>
  )
}
