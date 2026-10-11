import { useEffect, useMemo, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS } from '../helpers'
import { Icon } from '../ui'
import { btnGhost, btnPrimary, btnSecondary, card } from './styles'

type Rect = [number, number, number, number]
interface Box { id: number; b: Rect; label: string }
type Drag =
  | { kind: 'draw' | 'resize'; id: number; anchor: [number, number] }
  | { kind: 'move'; id: number; start: [number, number]; orig: Rect; client: [number, number] }

const TYPE_LABEL: Record<armor.FindingType, string> = {
  AADHAAR: 'Aadhaar number', VID: 'Aadhaar VID', MASKED_AADHAAR: 'Masked Aadhaar', PAN: 'PAN number',
  QR: 'QR code', BARCODE: 'Barcode', FACE: 'Photo', FINGERPRINT: 'Thumbprint', DOB: 'Date of birth',
  NUMBER: 'Other number', ADDRESS: 'Address', USER: 'Your box',
}
const TAGS = ['Signature', 'Address', 'Phone number', 'Photo']
const MIN_PX = 12
const LONG_PRESS_MS = 600

const norm = (a: [number, number], b: [number, number]): Rect => [
  Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1]),
]

/**
 * Manual redaction editor. The picture is the server's "before" view (thumbprints and QR codes
 * already pixelated), never the raw capture. Boxes are in image pixels, the same space the
 * server masks in. The user can only add hiding: green boxes the system found are locked.
 */
export default function RedactEditor({ jobId, result, onApply, onCancel }: {
  jobId: string
  result: armor.ArmorResult
  onApply: (boxes: armor.UserBox[]) => void
  onCancel: () => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<Drag | null>(null)
  const press = useRef<number | undefined>(undefined)
  const nextId = useRef(1)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  const [boxes, setBoxes] = useState<Box[]>(() =>
    result.findings.filter((f) => f.type === 'USER').map((f) => ({ id: nextId.current++, b: [...f.bbox_px] as Rect, label: f.label ?? '' })))
  const [sel, setSel] = useState<number | null>(null)
  const [extra, setExtra] = useState<Set<number>>(new Set())
  const [preview, setPreview] = useState(false)

  useEffect(() => () => window.clearTimeout(press.current), [])

  const locked = useMemo(() => result.findings.filter((f) => f.type !== 'USER' && f.action !== 'KEEP'), [result])
  const optional = useMemo(
    () => result.findings.map((f, i) => ({ f, i })).filter(({ f }) => f.action === 'KEEP' && f.type !== 'NUMBER' && f.type !== 'USER'),
    [result],
  )
  const selected = boxes.find((b) => b.id === sel) ?? null
  const changed = boxes.length > 0 || extra.size > 0

  const toImg = (e: { clientX: number; clientY: number }): [number, number] => {
    const m = svgRef.current?.getScreenCTM()
    if (!m || !size) return [0, 0]
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse())
    return [Math.min(size.w, Math.max(0, p.x)), Math.min(size.h, Math.max(0, p.y))]
  }
  const patch = (id: number, b: Rect) => setBoxes((bs) => bs.map((x) => (x.id === id ? { ...x, b } : x)))
  const remove = (id: number) => { setBoxes((bs) => bs.filter((x) => x.id !== id)); setSel(null) }

  const down = (e: React.PointerEvent<SVGSVGElement>) => {
    if (preview || !size) return
    const t = e.target as SVGElement
    const role = t.dataset.role
    const id = Number(t.dataset.id)
    const pt = toImg(e)
    svgRef.current?.setPointerCapture(e.pointerId)
    const box = boxes.find((b) => b.id === id)
    if (role === 'handle' && box) {
      const c = Number(t.dataset.corner)
      const corners: [number, number][] = [[box.b[0], box.b[1]], [box.b[2], box.b[1]], [box.b[2], box.b[3]], [box.b[0], box.b[3]]]
      drag.current = { kind: 'resize', id, anchor: corners[(c + 2) % 4] }
    } else if (role === 'box' && box) {
      setSel(id)
      drag.current = { kind: 'move', id, start: pt, orig: box.b, client: [e.clientX, e.clientY] }
      window.clearTimeout(press.current)
      press.current = window.setTimeout(() => { remove(id); drag.current = null }, LONG_PRESS_MS) // long-press deletes
    } else {
      const nid = nextId.current++
      setBoxes((bs) => [...bs, { id: nid, b: [pt[0], pt[1], pt[0], pt[1]], label: '' }])
      setSel(nid)
      drag.current = { kind: 'draw', id: nid, anchor: pt }
    }
  }
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current
    if (!d) return
    const pt = toImg(e)
    if (d.kind === 'move') {
      if (Math.hypot(e.clientX - d.client[0], e.clientY - d.client[1]) > 8) window.clearTimeout(press.current)
      const w = d.orig[2] - d.orig[0]
      const h = d.orig[3] - d.orig[1]
      const x = Math.min(size!.w - w, Math.max(0, d.orig[0] + pt[0] - d.start[0]))
      const y = Math.min(size!.h - h, Math.max(0, d.orig[1] + pt[1] - d.start[1]))
      patch(d.id, [x, y, x + w, y + h])
    } else {
      patch(d.id, norm(d.anchor, pt))
    }
  }
  const up = () => {
    window.clearTimeout(press.current)
    const d = drag.current
    drag.current = null
    if (!d) return
    const b = boxes.find((x) => x.id === d.id)
    if (b && d.kind !== 'move' && (b.b[2] - b.b[0] < MIN_PX || b.b[3] - b.b[1] < MIN_PX)) remove(d.id) // a tap, not a box
  }
  const key = (e: React.KeyboardEvent) => {
    if (sel !== null && (e.key === 'Delete' || e.key === 'Backspace')) { e.preventDefault(); remove(sel) }
  }

  const apply = () => {
    const out: armor.UserBox[] = boxes.map((b) => ({ bbox_px: b.b.map(Math.round) as Rect, label: b.label || null }))
    for (const i of extra) {
      const f = result.findings[i]
      out.push({ bbox_px: f.bbox_px.map(Math.round) as Rect, label: TYPE_LABEL[f.type] })
    }
    onApply(out)
  }

  const W = size?.w ?? 1
  const r = W / 90 // handle radius in image px
  const rect = (b: Rect | number[]) => ({ x: b[0], y: b[1], width: b[2] - b[0], height: b[3] - b[1] })

  return (
    <div className="fade-up space-y-5 lg:space-y-6">
      <div className="lg:text-center">
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 lg:text-3xl">Hide more on your copy</h2>
        <p className="mt-1 text-sm text-slate-600">
          Drag on the picture to cover anything else: a phone number, signature, address or photo. You can only add, never uncover what we already hide.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:items-start lg:gap-8">
        <section className={card} aria-label="Document editor">
          <div className="mb-3 inline-flex rounded-full bg-slate-100 p-1" role="group" aria-label="Preview mode">
            {([false, true] as const).map((p) => (
              <button key={String(p)} type="button" aria-pressed={preview === p} onClick={() => { setPreview(p); setSel(null) }}
                className={`min-h-10 rounded-full px-4 text-sm font-semibold transition ${preview === p ? 'bg-white text-accent-800 shadow-sm' : 'text-slate-600'}`}>
                {p ? 'What they will see' : 'Edit'}
              </button>
            ))}
          </div>
          <div className="relative select-none overflow-hidden rounded-2xl border border-slate-200 bg-slate-100">
            <img src={armor.viewUrl(jobId, 'before', false)} alt="Your document with sensitive parts pixelated" draggable={false}
              className="block h-auto w-full"
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })} />
            {size && (
              <svg ref={svgRef} viewBox={`0 0 ${size.w} ${size.h}`} className="absolute inset-0 h-full w-full"
                style={{ touchAction: preview ? 'auto' : 'none', cursor: preview ? 'default' : 'crosshair' }}
                tabIndex={0} role="application" aria-label="Draw boxes on the document. Press Delete to remove the selected box."
                onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onKeyDown={key}>
                {preview ? (
                  <>
                    {locked.flatMap((f) => f.masked_px).map((m, i) => <rect key={`l${i}`} {...rect(m)} fill="#000" />)}
                    {[...extra].map((i) => <rect key={`e${i}`} {...rect(result.findings[i].bbox_px)} fill="#000" />)}
                    {boxes.map((b) => <rect key={b.id} {...rect(b.b)} fill="#000" />)}
                  </>
                ) : (
                  <>
                    {locked.flatMap((f) => f.masked_px).map((m, i) => (
                      <rect key={`l${i}`} {...rect(m)} fill="#16a34a" fillOpacity=".28" stroke="#16a34a" strokeWidth="2" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                    ))}
                    {optional.map(({ f, i }) => !extra.has(i) && (
                      <rect key={`o${i}`} {...rect(f.bbox_px)} fill="none" stroke="#64748b" strokeDasharray="6 4" strokeWidth="2" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                    ))}
                    {[...extra].map((i) => (
                      <rect key={`e${i}`} {...rect(result.findings[i].bbox_px)} fill="#16a34a" fillOpacity=".4" stroke="#16a34a" strokeWidth="2" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                    ))}
                    {boxes.map((b) => (
                      <g key={b.id}>
                        <rect {...rect(b.b)} data-role="box" data-id={b.id} fill="#16a34a" fillOpacity=".4" stroke={b.id === sel ? '#0f766e' : '#16a34a'}
                          strokeWidth={b.id === sel ? 3 : 2} vectorEffect="non-scaling-stroke" style={{ cursor: 'move' }} />
                        {b.label && (
                          <text x={b.b[0] + r * 0.6} y={b.b[1] + r * 2} fontSize={r * 2} fill="#064e3b" stroke="#fff" strokeWidth={r * 0.5} paintOrder="stroke" pointerEvents="none">{b.label}</text>
                        )}
                        {b.id === sel && ([[b.b[0], b.b[1]], [b.b[2], b.b[1]], [b.b[2], b.b[3]], [b.b[0], b.b[3]]] as [number, number][]).map(([x, y], c) => (
                          <g key={c}>
                            <circle cx={x} cy={y} r={r} fill="#fff" stroke="#0f766e" strokeWidth="2" vectorEffect="non-scaling-stroke" pointerEvents="none" />
                            <circle cx={x} cy={y} r={r * 4} fill="transparent" data-role="handle" data-id={b.id} data-corner={c} style={{ cursor: 'nwse-resize' }} />
                          </g>
                        ))}
                      </g>
                    ))}
                  </>
                )}
              </svg>
            )}
            <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-slate-900/80 px-2.5 py-1 text-[11px] font-semibold text-white">
              {preview ? 'Preview · black bars' : 'Thumbprints and QR shown pixelated'}
            </span>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            <span className="font-semibold text-emerald-700">Green</span> = hidden. <span className="font-semibold text-slate-600">Grey dashed</span> = kept (tick it to hide).
            On a phone: drag to draw, drag a corner to resize, press and hold a box to delete it.
          </p>
        </section>

        <div className="space-y-5 lg:sticky lg:top-24">
          {selected && !preview && (
            <section className={`${card} space-y-3`} aria-label="Selected box">
              <h3 className="text-sm font-bold text-slate-900">Label this box <span className="font-normal text-slate-500">(optional)</span></h3>
              <div className="flex flex-wrap gap-2">
                {TAGS.map((t) => (
                  <button key={t} type="button" aria-pressed={selected.label === t}
                    onClick={() => setBoxes((bs) => bs.map((x) => (x.id === selected.id ? { ...x, label: x.label === t ? '' : t } : x)))}
                    className={`min-h-10 rounded-full px-3.5 text-xs font-semibold ring-1 transition ${selected.label === t ? 'bg-accent-700 text-white ring-accent-700' : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50'}`}>
                    {t}
                  </button>
                ))}
              </div>
              <button type="button" onClick={() => remove(selected.id)} className={`${btnSecondary} min-h-11 w-full text-red-700`}>Delete this box</button>
            </section>
          )}

          <section className={`${card} space-y-3`} aria-label="What is hidden">
            <h3 className="text-sm font-bold text-slate-900">What we found</h3>
            <ul className="space-y-2">
              {locked.map((f, i) => (
                <li key={`l${i}`} className="flex items-center gap-2.5 text-sm text-slate-800">
                  <Icon d={ICONS.shield} className="h-4 w-4 shrink-0 text-emerald-600" />
                  <span className="min-w-0 flex-1">{TYPE_LABEL[f.type]}</span>
                  <span className="text-xs font-medium text-emerald-700">Hidden</span>
                </li>
              ))}
              {optional.map(({ f, i }) => (
                <li key={`o${i}`}>
                  <label className="flex min-h-11 cursor-pointer items-center gap-2.5 text-sm text-slate-800">
                    <input type="checkbox" className="h-4 w-4 accent-teal-700" checked={extra.has(i)}
                      onChange={() => setExtra((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n })} />
                    <span className="min-w-0 flex-1">{TYPE_LABEL[f.type]}</span>
                    <span className="text-xs text-slate-500">{extra.has(i) ? 'Will hide' : 'Kept'}</span>
                  </label>
                </li>
              ))}
              {boxes.map((b, i) => (
                <li key={b.id} className="flex items-center gap-2.5 text-sm text-slate-800">
                  <Icon d={ICONS.eye} className="h-4 w-4 shrink-0 text-emerald-600" />
                  <button type="button" className="min-w-0 flex-1 text-left underline-offset-2 hover:underline" onClick={() => { setPreview(false); setSel(b.id) }}>
                    {b.label || `Your box ${i + 1}`}
                  </button>
                  <span className="text-xs font-medium text-emerald-700">Will hide</span>
                </li>
              ))}
            </ul>
          </section>

          <div className="flex items-center gap-3">
            <button type="button" onClick={onCancel} className={btnGhost}>Back</button>
            <button type="button" disabled={!changed} onClick={apply} className={`${btnPrimary} min-h-14 flex-1 text-base`}>
              Hide these and make a new copy
            </button>
          </div>
          <p className="text-xs text-slate-500">Making a new copy cancels the earlier one, so only the edited version can be used.</p>
        </div>
      </div>
    </div>
  )
}
