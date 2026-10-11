import { useEffect, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS } from '../helpers'
import { Icon } from '../ui'
import { RegionOverlay, VerdictCard } from './ForgeryView'
import { btnSecondary } from './styles'

const ATTACKS: [armor.AttackKind, string][] = [
  ['erase_watermark', 'Erase watermark'],
  ['swap_photo', 'Swap photo'],
  ['unmask', 'Unmask (brighten)'],
  ['crop', 'Crop'],
]

function Attacks({ id }: { id: string }) {
  const [busy, setBusy] = useState<armor.AttackKind | null>(null)
  const [res, setRes] = useState<armor.AttackResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const go = async (k: armor.AttackKind) => {
    setBusy(k)
    setError(null)
    try {
      setRes(await armor.attack(id, k))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The test failed')
    } finally {
      setBusy(null)
    }
  }
  return (
    <section>
      <h3 className="text-base font-semibold text-slate-900">Try to break it</h3>
      <p className="mt-1 text-sm text-slate-500">Tamper with the armored image and watch the sealed tile hashes catch it.</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {ATTACKS.map(([k, label]) => (
          <button key={k} type="button" disabled={busy !== null} onClick={() => void go(k)} className={btnSecondary}>
            {busy === k ? 'Attacking…' : label}
          </button>
        ))}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {res && (
        <div className="mt-4 space-y-3">
          <VerdictCard report={res.verify} flashKey={res.attack_id} expert />
          <RegionOverlay src={res.image_url} report={res.verify} alt="Tampered image with altered regions marked in red" />
        </div>
      )}
    </section>
  )
}

export default function Inspector({ id, onClose }: { id: string; onClose: () => void }) {
  const [data, setData] = useState<armor.Inspection | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    armor.getInspection(id).then(setData, (e: unknown) => setError(e instanceof Error ? e.message : 'Could not load inspection'))
  }, [id])

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-stretch md:justify-end" role="dialog" aria-modal="true" aria-label="Proof for experts">
      <button type="button" aria-label="Close proof panel" className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div className="sheet pb-safe relative flex max-h-[88vh] w-full flex-col rounded-t-2xl bg-white shadow-2xl md:max-h-none md:w-[32rem] md:rounded-none">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
            <Icon d={ICONS.inspect} className="h-5 w-5 text-indigo-700" />Proof for experts
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="flex h-11 w-11 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100">
            <Icon d={ICONS.x} className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-6 overflow-y-auto p-4">
          <p className="rounded-2xl bg-indigo-50 px-4 py-3 text-sm text-indigo-900 ring-1 ring-indigo-100">
            For judges and security reviewers: raw checks that the hidden parts are truly gone, plus a way to try to break the seal.
          </p>
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          {!data && !error && <p className="text-sm text-slate-500" role="status">Loading the proof…</p>}
          {data && (
            <>
              <section>
                <h3 className="text-base font-semibold text-slate-900">Mask forensics</h3>
                <div className="mt-2 space-y-2">
                  {data.masks.map((m, i) => (
                    <div key={i} className="rounded-xl bg-slate-50 p-3 text-xs ring-1 ring-slate-200">
                      <p className="font-mono text-slate-600">mask {i + 1} · [{m.bbox_px.join(', ')}]</p>
                      <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 sm:grid-cols-3">
                        <div><dt className="inline text-slate-500">pixels </dt><dd className="inline font-semibold tabular-nums">{m.pixels.toLocaleString()}</dd></div>
                        <div><dt className="inline text-slate-500">min </dt><dd className="inline font-semibold tabular-nums">{m.min}</dd></div>
                        <div><dt className="inline text-slate-500">max </dt><dd className="inline font-semibold tabular-nums">{m.max}</dd></div>
                        <div><dt className="inline text-slate-500">unique </dt><dd className="inline font-semibold tabular-nums">{m.unique_values}</dd></div>
                        <div className="col-span-2"><dt className="inline text-slate-500">entropy </dt><dd className="inline font-semibold tabular-nums">{m.entropy_bits.toFixed(3)} bits</dd></div>
                      </dl>
                      <p className="mt-1 break-all rounded bg-slate-900 px-2 py-1 font-mono text-emerald-300">{m.hex_sample}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-900 ring-1 ring-emerald-200">
                  Brightened ×255 → max {data.brightened_mask_max}. Nothing is hiding under the black.
                </p>
              </section>

              <section>
                <h3 className="text-base font-semibold text-slate-900">PDF facts</h3>
                <ul className="mt-2 space-y-1 text-sm text-slate-700">
                  <li>Text chars: <b>{data.pdf.text_chars}</b>{data.pdf.text_chars === 0 && ' — Select-all / copy returns nothing'}</li>
                  <li>Metadata: <code className="font-mono">{JSON.stringify(data.pdf.metadata)}</code></li>
                  <li>{data.pdf.images} image · {data.pdf.annotations} annotations · {data.pdf.pages} page</li>
                </ul>
              </section>

              <section>
                <h3 className="text-base font-semibold text-slate-900">PNG facts</h3>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {data.png.chunks.map((c, i) => <li key={i} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs">{c}</li>)}
                </ul>
                <p className="mt-2 text-sm text-slate-700">EXIF: <b>{data.png.exif ? 'present' : 'none'}</b></p>
              </section>
            </>
          )}
          <Attacks id={id} />
        </div>
      </div>
    </div>
  )
}
