import { useEffect, useRef, useState, type PointerEvent } from 'react'

type Preset = 'Hotel Check-in' | 'Xerox / Print Shop' | 'SIM / Telecom' | 'Rental / Landlord' | 'School Admission' | 'Bank Loan'
type IDType = 'aadhaar' | 'pan' | 'passport' | 'voter' | 'driving_license' | 'other'
type Box = { x: number; y: number; w: number; h: number; style: 'blur' | 'black'; kind: string; automatic?: boolean }
type ScanResult = { width: number; height: number; ocr_quality: number; recognized_word_count: number; verifiable: boolean; detections: { type: string; box: [number, number, number, number]; confidence: number }[] }
const presets: Record<Preset, string> = {
  'Hotel Check-in': 'Aadhaar first 8 digits, QR/barcode and biometrics',
  'Xerox / Print Shop': 'All identity numbers; keep only name and photo',
  'SIM / Telecom': 'Aadhaar first 8 digits, QR/barcode and biometrics',
  'Rental / Landlord': 'Aadhaar first 8 digits, QR/barcode and biometrics',
  'School Admission': 'Aadhaar first 8 digits, QR/barcode and biometrics',
  'Bank Loan': 'Aadhaar first 8 digits, QR/barcode and biometrics',
}

function dateLabel() {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date()).toUpperCase()
}
function randomCode() {
  const bytes = crypto.getRandomValues(new Uint8Array(6))
  return Array.from(bytes, (n) => n.toString(16).padStart(2, '0')).join('').toUpperCase()
}

export default function SurakshitID() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const sourceRef = useRef<HTMLImageElement | null>(null)
  const objectUrl = useRef<string | null>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)
  const [preset, setPreset] = useState<Preset>('Hotel Check-in')
  const [idType, setIdType] = useState<IDType>('aadhaar')
  const [maskStyle, setMaskStyle] = useState<'blur' | 'black'>('blur')
  const [purpose, setPurpose] = useState('GOA TAJ HOTEL CHECK-IN')
  const [boxes, setBoxes] = useState<Box[]>([])
  const [draft, setDraft] = useState<Box | null>(null)
  const [error, setError] = useState('')
  const [warning, setWarning] = useState('')
  const [quality, setQuality] = useState<number | null>(null)
  const [output, setOutput] = useState<{ url: string; hash: string; code: string } | null>(null)
  const [inspector, setInspector] = useState(false)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanReady, setScanReady] = useState(false)
  const fileRef = useRef<File | null>(null)
  const scanRun = useRef(0)
  const baselineRef = useRef<{ width: number; height: number; data: Uint8ClampedArray } | null>(null)
  const [tamperResult, setTamperResult] = useState<{ changed: boolean; bounds: [number, number, number, number] | null } | null>(null)

  useEffect(() => {
    if (videoRef.current && streamRef.current) videoRef.current.srcObject = streamRef.current
  }, [cameraOpen])
  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), [])

  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current) }, [])
  useEffect(() => () => { if (output) URL.revokeObjectURL(output.url) }, [output?.url])

  const paint = (image: HTMLImageElement, masks: Box[], withMark: boolean, token = randomCode()) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!
    const scale = Math.min(1, 1400 / image.naturalWidth, 1400 / image.naturalHeight)
    canvas.width = Math.round(image.naturalWidth * scale)
    canvas.height = Math.round(image.naturalHeight * scale)
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    if (withMark) {
      const label = `FOR ${purpose || 'SPECIFIED PURPOSE'} ONLY · ${dateLabel()} · ${token} · NOT VALID FOR OTHER USES`
      ctx.save()
      ctx.globalAlpha = 0.62
      ctx.fillStyle = '#0f3d38'
      let fontSize = Math.max(9, Math.min(22, canvas.width / 44))
      ctx.font = `700 ${fontSize}px sans-serif`
      while (fontSize > 9 && ctx.measureText(label).width > canvas.width * 0.92) {
        fontSize -= 1; ctx.font = `700 ${fontSize}px sans-serif`
      }
      ctx.lineWidth = Math.max(2, fontSize / 5); ctx.strokeStyle = 'rgba(255,255,255,.78)'
      const alternate = `SURAKSHITID · ${token} · NOT VALID FOR OTHER USES`
      const stepX = Math.max(ctx.measureText(label).width, ctx.measureText(alternate).width) + fontSize * 2.5
      const stepY = fontSize * 5
      const diagonal = Math.hypot(canvas.width, canvas.height)
      ctx.translate(canvas.width / 2, canvas.height / 2); ctx.rotate(-Math.PI / 5)
      let row = 0
      for (let y = -diagonal; y < diagonal; y += stepY, row++) {
        const text = row % 2 === 0 ? label : alternate
        for (let x = -diagonal; x < diagonal; x += stepX) { ctx.strokeText(text, x, y); ctx.fillText(text, x, y) }
      }
      ctx.restore()
    }
    // Solid black (RGB 0,0,0) is written into the flattened raster; masks are applied last.
    for (const b of [...masks].sort((a, b) => Number(a.style === 'black') - Number(b.style === 'black'))) {
      if (b.style === 'black') ctx.fillRect(b.x, b.y, b.w, b.h)
      else {
        const block = Math.max(8, Math.round(Math.min(b.w, b.h) / 12))
        const sw = Math.max(1, Math.ceil(b.w / block)), sh = Math.max(1, Math.ceil(b.h / block))
        const tiny = document.createElement('canvas'); tiny.width = sw; tiny.height = sh
        tiny.getContext('2d')!.drawImage(ctx.canvas, b.x, b.y, b.w, b.h, 0, 0, sw, sh)
        ctx.save(); ctx.imageSmoothingEnabled = false; ctx.drawImage(tiny, 0, 0, sw, sh, b.x, b.y, b.w, b.h); ctx.restore()
      }
    }
    return ctx
  }

  const load = (file?: File) => {
    if (!file) return
    scanRun.current += 1
    setScanning(false)
    fileRef.current = file
    sourceRef.current = null
    baselineRef.current = null
    setTamperResult(null)
    setError(''); setWarning(''); setOutput(null); setBoxes([]); setQuality(null); setScanReady(false)
    if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
      sourceRef.current = null
      setError('Cannot verify safely: this local build cannot rasterize PDFs. Use a page image; PDF support will be enabled with a verified local rasterizer.')
      return
    }
    if (!file.type.startsWith('image/')) { sourceRef.current = null; setError('Choose a supported image file.'); return }
    const url = URL.createObjectURL(file)
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
    objectUrl.current = url
    const image = new Image()
    image.onload = () => {
      sourceRef.current = image
      const scale = Math.min(1, 1400 / image.naturalWidth, 1400 / image.naturalHeight)
      const probe = document.createElement('canvas')
      probe.width = Math.round(image.naturalWidth * scale); probe.height = Math.round(image.naturalHeight * scale)
      const probeContext = probe.getContext('2d', { willReadFrequently: true })!
      probeContext.drawImage(image, 0, 0, probe.width, probe.height)
      const { width, height } = probe
      const pixels = probeContext.getImageData(0, 0, width, height).data
      // Laplacian variance is used only as a conservative blur gate, never as proof of document safety.
      let sum = 0, sumSq = 0, count = 0
      const stride = Math.max(1, Math.floor(Math.max(width, height) / 500))
      for (let y = stride; y < height - stride; y += stride) for (let x = stride; x < width - stride; x += stride) {
        const i = (y * width + x) * 4
        const gray = (j: number) => (pixels[j] * .299 + pixels[j + 1] * .587 + pixels[j + 2] * .114)
        const v = gray(i - width * 4) + gray(i + width * 4) + gray(i - 4) + gray(i + 4) - 4 * gray(i)
        sum += v; sumSq += v * v; count++
      }
      const variance = count ? sumSq / count - (sum / count) ** 2 : 0
      setQuality(Math.round(variance))
      if (variance < 20) setError('Cannot verify safely: this image appears blurry or unreadable. Capture a sharper image before continuing.')
    }
    image.onerror = () => setError('Cannot verify safely: the image could not be decoded.')
    image.src = url
    void scanFile(file, idType)
  }
  const scanFile = async (file: File, selectedType: IDType) => {
    const run = ++scanRun.current
    setScanning(true); setScanReady(false); setError(''); setWarning(''); setBoxes([])
    const form = new FormData(); form.append('file', file)
    try {
      const response = await fetch(`/api/surakshit/scan-image?id_type=${selectedType}`, { method: 'POST', body: form })
      const body = await response.json()
      if (run !== scanRun.current) return
      if (!response.ok) throw new Error(body.detail || 'local scan failed')
      const result = body as ScanResult
      const scale = Math.min(1, 1400 / result.width, 1400 / result.height)
      const automatic: Box[] = result.detections.map((d) => ({ x: d.box[0] * scale, y: d.box[1] * scale, w: (d.box[2] - d.box[0]) * scale, h: (d.box[3] - d.box[1]) * scale, style: maskStyle, kind: d.type, automatic: true }))
      setBoxes(automatic)
      if (!result.verifiable) throw new Error('local OCR could not read any text; use a sharper, well-lit image')
      setScanReady(true)
      const warnings: string[] = []
      if (result.ocr_quality < 0.55) warnings.push('OCR confidence is low; automatic detection may have missed sensitive fields. Inspect the full document and add masks manually.')
      if (automatic.length === 0) warnings.push('No matching fields detected. Check the ID type, inspect the whole image, and add masks manually.')
      setWarning(warnings.join(' '))
    } catch (e) {
      if (run === scanRun.current) setError(e instanceof Error ? `Cannot verify safely: ${e.message}` : 'Cannot verify safely: local scan failed.')
    } finally { if (run === scanRun.current) setScanning(false) }
  }
  const openCamera = async () => {
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      setCameraOpen(true)
    } catch { setError('Camera unavailable. Check browser permission or choose an image file.') }
  }
  const captureCamera = () => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const capture = document.createElement('canvas')
    capture.width = video.videoWidth; capture.height = video.videoHeight
    capture.getContext('2d')?.drawImage(video, 0, 0)
    capture.toBlob((blob) => {
      if (blob) load(new File([blob], 'camera-capture.png', { type: 'image/png' }))
      streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; setCameraOpen(false)
    }, 'image/png')
  }

  const coordinates = (e: PointerEvent<HTMLCanvasElement>) => {
    const c = e.currentTarget.getBoundingClientRect()
    return { x: (e.clientX - c.left) * e.currentTarget.width / c.width, y: (e.clientY - c.top) * e.currentTarget.height / c.height }
  }
  const begin = (e: PointerEvent<HTMLCanvasElement>) => { if (!sourceRef.current || !scanReady || scanning || (quality !== null && quality < 20)) return; e.currentTarget.setPointerCapture(e.pointerId); dragStart.current = coordinates(e); setDraft({ ...dragStart.current, w: 0, h: 0, style: maskStyle, kind: 'MANUAL' }) }
  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!dragStart.current) return
    const p = coordinates(e), s = dragStart.current
    setDraft({ x: Math.min(p.x, s.x), y: Math.min(p.y, s.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y), style: maskStyle, kind: 'MANUAL' })
  }
  const end = () => { if (draft && draft.w > 5 && draft.h > 5) setBoxes((old) => [...old, draft]); dragStart.current = null; setDraft(null) }
  const redraw = () => {
    if (sourceRef.current && scanReady && quality !== null && quality >= 20) {
      paint(sourceRef.current, [...boxes, ...(draft ? [draft] : [])], false)
    }
  }
  useEffect(redraw, [boxes, draft, scanReady, quality])

  const exportImage = async () => {
    if (!sourceRef.current || error || !scanReady || scanning || quality === null || quality < 20) { setError('Cannot verify safely. Wait for local scanning and use a readable image.'); return }
    if (!boxes.length) { setError('Add at least one mask area before exporting. Review the full document and mark every sensitive region.'); return }
    setError('')
    const code = randomCode()
    const ctx = paint(sourceRef.current, boxes, true, code)
    if (!ctx) return
    // For solid masks, write RGB zero bytes after watermarking. Blur masks stay pixelated.
    const imageData = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height)
    for (const b of boxes.filter((box) => box.style === 'black')) {
      const x0 = Math.max(0, Math.floor(b.x)), y0 = Math.max(0, Math.floor(b.y)), x1 = Math.min(ctx.canvas.width, Math.ceil(b.x + b.w)), y1 = Math.min(ctx.canvas.height, Math.ceil(b.y + b.h))
      for (let y = y0; y < y1; y += 1) for (let x = x0; x < x1; x += 1) {
        const i = (y * ctx.canvas.width + x) * 4
        imageData.data[i] = imageData.data[i + 1] = imageData.data[i + 2] = 0; imageData.data[i + 3] = 255
      }
    }
    baselineRef.current = { width: ctx.canvas.width, height: ctx.canvas.height, data: new Uint8ClampedArray(imageData.data) }
    ctx.putImageData(imageData, 0, 0)
    for (const b of boxes.filter((box) => box.style === 'black')) {
      const x = Math.max(0, Math.floor(b.x)), y = Math.max(0, Math.floor(b.y)), i = (y * ctx.canvas.width + x) * 4
      if (imageData.data[i] !== 0 || imageData.data[i + 1] !== 0 || imageData.data[i + 2] !== 0 || imageData.data[i + 3] !== 255) { setError('Cannot verify safely: mask pixel verification failed.'); return }
    }
    const blob = await new Promise<Blob | null>((resolve) => ctx.canvas.toBlob(resolve, 'image/png'))
    if (!blob) { setError('Cannot verify safely: flattened export failed.'); return }
    const bytes = await blob.arrayBuffer()
    const digest = await crypto.subtle.digest('SHA-256', bytes)
    const hash = Array.from(new Uint8Array(digest), (n) => n.toString(16).padStart(2, '0')).join('')
    const url = URL.createObjectURL(blob)
    setOutput({ url, hash, code })
    setTamperResult(null)
    setInspector(true)
  }

  const verifyEditedCopy = async (file?: File) => {
    const baseline = baselineRef.current
    if (!file || !baseline) return
    const url = URL.createObjectURL(file)
    try {
      const image = await new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new Image(); img.onload = () => resolve(img); img.onerror = reject; img.src = url
      })
      const check = document.createElement('canvas'); check.width = baseline.width; check.height = baseline.height
      const ctx = check.getContext('2d', { willReadFrequently: true })!
      ctx.drawImage(image, 0, 0, check.width, check.height)
      const observed = ctx.getImageData(0, 0, check.width, check.height).data
      let x0 = check.width, y0 = check.height, x1 = -1, y1 = -1
      for (let y = 0; y < check.height; y++) for (let x = 0; x < check.width; x++) {
        const i = (y * check.width + x) * 4
        if (Math.abs(observed[i] - baseline.data[i]) > 18 || Math.abs(observed[i + 1] - baseline.data[i + 1]) > 18 || Math.abs(observed[i + 2] - baseline.data[i + 2]) > 18 || observed[i + 3] !== baseline.data[i + 3]) {
          x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y)
        }
      }
      setTamperResult({ changed: x1 >= 0, bounds: x1 >= 0 ? [x0, y0, x1 + 1, y1 + 1] : null })
    } catch { setTamperResult({ changed: true, bounds: [0, 0, baseline.width, baseline.height] }) }
    finally { URL.revokeObjectURL(url) }
  }

  const showPreview = Boolean(sourceRef.current && scanReady && quality !== null && quality >= 20)
  return <section className="mx-auto max-w-5xl">
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div><h2 className="text-xl font-semibold tracking-tight text-slate-900">Purpose-locked identity copy</h2><p className="mt-1 text-sm text-slate-500">Create a flattened, watermarked image for one stated use.</p></div>
      <span className="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">Local image prototype · manual review required</span>
    </div>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <div className="flex flex-wrap gap-2">
          <label className="cursor-pointer rounded-lg bg-accent-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-accent-800">Choose image<input className="sr-only" type="file" accept="image/*,application/pdf,.pdf" onChange={(e) => { load(e.target.files?.[0]); e.currentTarget.value = '' }} /></label>
          <button type="button" onClick={() => void openCamera()} className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Open camera</button>
          {boxes.some((b) => !b.automatic) && <button type="button" onClick={() => setBoxes((old) => old.filter((b) => b.automatic))} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Clear manual masks</button>}
        </div>
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
          {cameraOpen && <div className="relative border-b border-slate-200 bg-slate-900"><video ref={videoRef} autoPlay playsInline className="block max-h-[65vh] w-full object-contain" /><div aria-hidden="true" className="pointer-events-none absolute inset-[8%] rounded-xl border-2 border-dashed border-white/80"><span className="absolute left-1/2 top-2 -translate-x-1/2 rounded bg-black/50 px-2 py-1 text-xs text-white">Align document inside frame</span></div><div className="absolute inset-x-0 bottom-3 flex justify-center gap-2"><button type="button" onClick={captureCamera} className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-slate-900">Capture</button><button type="button" onClick={() => { streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; setCameraOpen(false) }} className="rounded-full bg-black/60 px-4 py-2 text-sm font-medium text-white">Cancel</button></div></div>}
          <canvas ref={canvasRef} onPointerDown={begin} onPointerMove={move} onPointerUp={end} onPointerCancel={end} className={`${showPreview ? 'block' : 'hidden'} h-auto max-h-[70vh] w-full touch-none object-contain`} aria-label="Document preview with detected sensitive areas blurred. Drag to add mask areas." />
          {!showPreview && <div className="flex min-h-64 flex-col items-center justify-center px-6 text-center text-slate-500"><div className="text-sm font-medium text-slate-700">{scanning ? 'Scanning locally before showing the preview…' : 'Capture or select a document image'}</div><div className="mt-1 text-xs">The unprocessed image stays hidden until scanning finishes.</div></div>}
          {showPreview && <p className="border-t border-slate-200 px-3 py-2 text-xs text-slate-500">Detected fields are blurred{boxes.some((b) => b.automatic) ? `: ${Array.from(new Set(boxes.filter((b) => b.automatic).map((b) => b.kind))).join(', ')}` : ''}. Drag to add masks over any sensitive fields the scan missed.</p>}
        </div>
        {scanning && <p className="mt-3 text-sm text-accent-800">Scanning locally for {idType.replace('_', ' ')} fields and pre-blurring matches…</p>}
        {scanReady && <p className="mt-3 text-xs text-emerald-700">Local scan complete · {boxes.filter((b) => b.automatic).length} areas pre-blurred · inspect the full document for missed fields.</p>}
        {quality !== null && <p className={`mt-2 text-xs ${quality < 20 ? 'text-red-700' : 'text-emerald-700'}`}>Image clarity gate: {quality < 20 ? 'failed · cannot verify safely' : 'passed'} · OCR and visual review still have limits.</p>}
        {warning && <p role="status" className="mt-3 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">{warning}</p>}
        {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800 ring-1 ring-red-200">{error}</p>}
        {output && <div className="mt-4 rounded-xl bg-emerald-50 p-4 ring-1 ring-emerald-200"><div className="text-sm font-semibold text-emerald-900">Raster checks passed</div><p className="mt-1 break-all font-mono text-xs text-emerald-800">SHA-256 {output.hash}</p><a href={output.url} download="surakshitid-purpose-copy.png" className="mt-3 inline-flex rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800">Download flattened PNG</a><button type="button" onClick={() => setInspector(true)} className="ml-3 mt-3 text-sm font-medium text-emerald-800 underline">Adversarial inspector</button></div>}
      </div>
      <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900">Document &amp; sharing purpose</h3>
        <label className="mt-4 block text-xs font-medium text-slate-600">Identity document type<select className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm" value={idType} onChange={(e) => { const next = e.target.value as IDType; const file = fileRef.current; setIdType(next); if (file?.type.startsWith('image/')) void scanFile(file, next) }}><option value="aadhaar">Aadhaar</option><option value="pan">PAN</option><option value="passport">Passport</option><option value="voter">Voter ID</option><option value="driving_license">Driving licence</option><option value="other">Other / scan common IDs</option></select></label>
        <label className="mt-4 block text-xs font-medium text-slate-600">Everyday preset<select className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm" value={preset} onChange={(e) => setPreset(e.target.value as Preset)}>{Object.keys(presets).map((p) => <option key={p}>{p}</option>)}</select></label>
        <label className="mt-3 block text-xs font-medium text-slate-600">Specific recipient / purpose<input value={purpose} onChange={(e) => setPurpose(e.target.value.toUpperCase())} maxLength={72} className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm" /></label>
        <div className="mt-4 rounded-lg bg-accent-50 p-3 text-xs leading-5 text-accent-900"><strong>Preset guidance:</strong> {presets[preset]}. Detected fields are pixel-blurred before review; inspect and add any missed regions.</div>
        <label className="mt-3 block text-xs font-medium text-slate-600">Additional mask style<select value={maskStyle} onChange={(e) => { const style = e.target.value as 'blur' | 'black'; setMaskStyle(style); setBoxes((old) => old.map((b) => b.automatic ? { ...b, style } : b)) }} className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm"><option value="blur">Pixel blur</option><option value="black">Solid black redaction</option></select></label>
        <p className="mt-2 text-[11px] leading-4 text-amber-800">Use solid black for high-risk numbers. Blur improves readability but may be weaker against reconstruction.</p>
        <div className="mt-4 flex items-start gap-2 text-xs leading-5 text-slate-500"><span className="mt-0.5 text-accent-700">●</span><span>Watermark includes recipient, date, and random token. PNG is flattened and metadata-free.</span></div>
        <button type="button" onClick={() => void exportImage()} disabled={!sourceRef.current || quality === null || quality < 20 || !scanReady || scanning} className="mt-5 w-full rounded-lg bg-accent-700 px-4 py-3 text-sm font-semibold text-white hover:bg-accent-800 disabled:cursor-not-allowed disabled:opacity-40">Armor &amp; issue copy</button>
      </aside>
    </div>
    {inspector && output && <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/40 p-3 sm:items-center" role="presentation" onClick={() => setInspector(false)}><section role="dialog" aria-modal="true" aria-labelledby="inspect-title" onClick={(e) => e.stopPropagation()} className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"><div className="flex items-center justify-between"><h3 id="inspect-title" className="font-semibold text-slate-900">Adversarial Inspector</h3><button type="button" onClick={() => setInspector(false)} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close inspector">✕</button></div><p className="mt-3 text-sm text-slate-600">The tiled watermark is repeated at measured spacing to avoid overlaps. Compare a suspected edited copy against the in-session original below.</p><dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between gap-4"><dt className="text-slate-500">Mask regions</dt><dd className="font-medium text-slate-900">{boxes.length} · {boxes.filter((b) => b.style === 'black').length} solid black · {boxes.filter((b) => b.style === 'blur').length} pixel-blurred</dd></div><div className="flex justify-between gap-4"><dt className="text-slate-500">Selectable text / hidden layers</dt><dd className="font-medium text-slate-900">None · raster PNG</dd></div><div><dt className="text-slate-500">SHA-256</dt><dd className="mt-1 break-all font-mono text-xs text-slate-700">{output.hash}</dd></div><div><dt className="text-slate-500">Watermark token</dt><dd className="mt-1 font-mono text-xs text-slate-700">{output.code}</dd></div></dl><label className="mt-5 block text-sm font-medium text-slate-800">Check a copy for edits<input type="file" accept="image/*" className="mt-2 block w-full text-xs text-slate-600" onChange={(e) => { void verifyEditedCopy(e.target.files?.[0]); e.currentTarget.value = '' }} /></label>{tamperResult && <div role="status" className={`mt-3 rounded-lg p-3 text-sm font-semibold ${tamperResult.changed ? 'bg-red-50 text-red-800 ring-1 ring-red-200' : 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200'}`}>{tamperResult.changed ? `FORGERY DETECTED · changed area x:${tamperResult.bounds?.[0]}, y:${tamperResult.bounds?.[1]} to x:${tamperResult.bounds?.[2]}, y:${tamperResult.bounds?.[3]}` : 'MATCH · no changed pixels found'}</div>}<p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900">This check compares against the original retained in this browser session; it does not make a watermark impossible to remove or work as a portable signature after the session ends.</p></section></div>}
  </section>
}
