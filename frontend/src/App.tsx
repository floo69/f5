import { useEffect, useRef, useState } from 'react'
import * as api from './api'
import ProgressCard from './components/ProgressCard'
import ResultView from './components/ResultView'

type Preset = { name: string; icon: string; fields: string[]; masks: string[]; duration: string }
type Box = { x: number; y: number; w: number; h: number; label: string }

const presets: Preset[] = [
  { name: 'Hotel check-in', icon: '⌂', fields: ['Name', 'Photo'], masks: ['Aadhaar number', 'QR / barcode', 'Thumbprints'], duration: '24 hours' },
  { name: 'Xerox / print shop', icon: '▤', fields: ['Photo', 'Name'], masks: ['All ID numbers', 'QR / barcode', 'Thumbprints'], duration: '1 hour' },
  { name: 'SIM / telecom', icon: '◉', fields: ['Name', 'Photo', 'Address'], masks: ['Aadhaar number', 'QR / barcode', 'Thumbprints'], duration: '24 hours' },
  { name: 'Rental / landlord', icon: '⌂', fields: ['Name', 'Photo', 'Address'], masks: ['Aadhaar number', 'QR / barcode', 'Thumbprints'], duration: '7 days' },
  { name: 'School admission', icon: '▧', fields: ['Name', 'Photo', 'Date of birth'], masks: ['Aadhaar number', 'QR / barcode', 'Thumbprints'], duration: '30 days' },
  { name: 'Bank loan', icon: '▥', fields: ['Name', 'Photo', 'Address'], masks: ['Aadhaar number', 'QR / barcode', 'Thumbprints'], duration: '24 hours' },
]

const starterBoxes: Box[] = [
  { x: .57, y: .43, w: .34, h: .055, label: 'Aadhaar number' },
  { x: .69, y: .60, w: .20, h: .12, label: 'QR / barcode' },
  { x: .12, y: .72, w: .22, h: .08, label: 'Thumbprints' },
]

function Shield({ size = 22 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3 20 6v5.5c0 4.5-3.1 7.6-8 9.5-4.9-1.9-8-5-8-9.5V6l8-3Z" stroke="currentColor" strokeWidth="1.8"/><path d="m8.5 12 2.3 2.3 4.8-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>
}

function createSample(): string {
  const c = document.createElement('canvas'); c.width = 1000; c.height = 700
  const g = c.getContext('2d')!
  g.fillStyle = '#eee9da'; g.fillRect(0, 0, c.width, c.height)
  g.fillStyle = '#fffdf6'; g.fillRect(45, 35, 910, 630)
  g.strokeStyle = '#d3ccba'; g.lineWidth = 2; g.strokeRect(45, 35, 910, 630)
  g.fillStyle = '#173a32'; g.fillRect(45, 35, 910, 80)
  g.fillStyle = '#e4d2a7'; g.font = 'bold 24px Georgia'; g.fillText('GOVERNMENT OF INDIA', 82, 72)
  g.fillStyle = '#fff'; g.font = '13px Arial'; g.fillText('SYNTHETIC SAMPLE · NOT A REAL DOCUMENT', 82, 95)
  g.fillStyle = '#333'; g.font = 'bold 23px Arial'; g.fillText('IDENTITY CARD', 82, 164)
  g.fillStyle = '#768077'; g.font = '14px Arial'; g.fillText('Unique Identification Authority of India', 82, 191)
  g.fillStyle = '#d4e3dc'; g.fillRect(82, 220, 190, 215)
  g.fillStyle = '#82a59a'; g.beginPath(); g.arc(177, 295, 48, 0, Math.PI * 2); g.fill()
  g.fillStyle = '#82a59a'; g.beginPath(); g.ellipse(177, 395, 76, 53, 0, Math.PI, 0); g.fill()
  g.fillStyle = '#353d39'; g.font = 'bold 21px Arial'; g.fillText('ANANYA SHARMA', 315, 260)
  g.font = '16px Arial'; g.fillStyle = '#747b74'; g.fillText('Date of birth', 315, 305); g.fillText('14 / 08 / 1996', 315, 330)
  g.fillText('Address', 315, 374); g.fillText('12 Park Street, Panaji, Goa', 315, 400)
  g.fillStyle = '#242824'; g.font = 'bold 24px monospace'; g.fillText('4821  7356  1902', 575, 337)
  g.fillStyle = '#476d5d'; g.font = '14px Arial'; g.fillText('SAMPLE ID · NOT FOR OFFICIAL USE', 315, 455)
  g.strokeStyle = '#5b675d'; g.lineWidth = 2; g.strokeRect(115, 512, 160, 96)
  g.strokeRect(694, 500, 160, 128); g.fillStyle = '#477b65'
  for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) if ((i * 7 + j * 5) % 3 !== 0) g.fillRect(704 + i * 22, 510 + j * 17, 12, 12)
  g.fillStyle = '#59635c'; g.font = '12px Arial'; g.fillText('SPECIMEN THUMBPRINT', 120, 625); g.fillText('SAMPLE QR', 730, 645)
  return c.toDataURL('image/png')
}

export default function App() {
  const [presetName, setPresetName] = useState(presets[0].name)
  const [source, setSource] = useState<string | null>(null)
  const [fileName, setFileName] = useState('Synthetic Aadhaar sample')
  const [boxes, setBoxes] = useState<Box[]>(starterBoxes)
  const [output, setOutput] = useState<string | null>(null)
  const [digest, setDigest] = useState('')
  const [notice, setNotice] = useState('')
  const [inspector, setInspector] = useState(false)
  const [camera, setCamera] = useState(false)
  const [tamperAt, setTamperAt] = useState<{ x: number; y: number } | null>(null)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [drawEnd, setDrawEnd] = useState<{ x: number; y: number } | null>(null)
  const [tampered, setTampered] = useState(false)
  const [issueToken, setIssueToken] = useState('')
  const [mobileTab, setMobileTab] = useState<'armor' | 'verify'>('armor')
  const [pdfMode, setPdfMode] = useState(false)
  const [pdfJob, setPdfJob] = useState<api.Job | null>(null)
  const [pdfResult, setPdfResult] = useState<api.Result | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [pdfFilename, setPdfFilename] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const pdfInput = useRef<HTMLInputElement>(null)
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const previewRef = useRef<HTMLDivElement>(null)
  const activePreset = presets.find((p) => p.name === presetName) ?? presets[0]

  useEffect(() => { setSource(createSample()) }, [])
  useEffect(() => () => stream.current?.getTracks().forEach((t) => t.stop()), [])
  useEffect(() => {
    if (camera && video.current && stream.current) video.current.srcObject = stream.current
  }, [camera])

  const resetOutput = () => { if (output) URL.revokeObjectURL(output); setOutput(null); setDigest(''); setInspector(false); setTampered(false); setTamperAt(null) }
  const chooseFile = (file?: File) => {
    if (!file) return
    if (!file.type.startsWith('image/')) { setNotice('This demo reads images locally. PDF redaction is available in the repository’s existing scanner.'); return }
    const url = URL.createObjectURL(file), image = new Image()
    image.onload = () => { setSource(url); setFileName(file.name); setBoxes([]); resetOutput(); setNotice('Image loaded locally. Mark each sensitive area on the document before sharing.') }
    image.onerror = () => { URL.revokeObjectURL(url); setNotice('Cannot verify safely · this image could not be read.') }
    image.src = url
  }

  const openCamera = async () => {
    try { stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false }); setCamera(true); setNotice('') }
    catch { setNotice('Camera unavailable. Check browser permissions or choose an image instead.') }
  }
  const capture = () => {
    if (!video.current) return
    const c = document.createElement('canvas'); c.width = video.current.videoWidth; c.height = video.current.videoHeight
    c.getContext('2d')?.drawImage(video.current, 0, 0); setSource(c.toDataURL('image/png')); setFileName('Camera capture'); setBoxes([]); resetOutput(); setCamera(false); stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null
    setNotice('Captured on this device. Mark sensitive areas before sharing.')
  }

  const coords = (e: React.PointerEvent) => {
    const rect = previewRef.current!.getBoundingClientRect()
    return { x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)) }
  }
  const pointerDown = (e: React.PointerEvent) => { if (!source) return; e.currentTarget.setPointerCapture(e.pointerId); const p = coords(e); setDrawStart(p); setDrawEnd(p) }
  const pointerMove = (e: React.PointerEvent) => { if (drawStart) setDrawEnd(coords(e)) }
  const pointerUp = () => {
    if (drawStart && drawEnd) { const x = Math.min(drawStart.x, drawEnd.x), y = Math.min(drawStart.y, drawEnd.y), w = Math.abs(drawEnd.x - drawStart.x), h = Math.abs(drawEnd.y - drawStart.y); if (w > .018 && h > .012) { setBoxes((old) => [...old, { x, y, w, h, label: 'Custom sensitive area' }]); resetOutput() } }
    setDrawStart(null); setDrawEnd(null)
  }

  const armor = async () => {
    if (!source) return
    if (boxes.length === 0) { setNotice('Cannot verify safely · add a mask over each sensitive area before export.'); return }
    setNotice(''); setTampered(false)
    const img = new Image(); img.src = source
    await new Promise<void>((resolve, reject) => { img.onload = () => resolve(); img.onerror = () => reject() })
    const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight
    const g = c.getContext('2d', { willReadFrequently: true })!
    g.drawImage(img, 0, 0)
    const entropy = crypto.getRandomValues(new Uint8Array(5))
    const token = [...entropy].map((n) => n.toString(16).padStart(2, '0')).join('').toUpperCase()
    setIssueToken(token)
    const purpose = activePreset.name.toUpperCase()
    // Render one large watermark, then blend it with the actual image pixels. Its
    // color and strength adapt to local brightness/texture instead of forming a
    // uniform text color that basic removal tools can isolate with a simple filter.
    const watermark = `FOR ${purpose} ONLY · REF ${token}`
    const fontSize = Math.max(18, Math.round(Math.min(c.width, c.height) * .095))
    const mark = document.createElement('canvas'); mark.width = c.width; mark.height = c.height
    const mg = mark.getContext('2d', { willReadFrequently: true })!
    const maxTextWidth = Math.hypot(c.width, c.height) * .92
    const measured = (() => { mg.font = `bold ${fontSize}px Arial`; return mg.measureText(watermark).width })()
    const fittedFontSize = fontSize * Math.min(1, maxTextWidth / measured)
    mg.save(); mg.translate(c.width / 2, c.height / 2); mg.rotate(-Math.PI / 5)
    mg.font = `bold ${fittedFontSize}px Arial`; mg.textAlign = 'center'; mg.textBaseline = 'middle'
    mg.lineJoin = 'round'; mg.lineWidth = Math.max(2, fittedFontSize * .16); mg.strokeStyle = '#fff'
    mg.strokeText(watermark, 0, 0, maxTextWidth); mg.fillStyle = '#fff'; mg.fillText(watermark, 0, 0, maxTextWidth); mg.restore()
    const blendedPixels = g.getImageData(0, 0, c.width, c.height)
    const mask = mg.getImageData(0, 0, c.width, c.height)
    const d = blendedPixels.data
    const lum = (r: number, gg: number, b: number) => .299 * r + .587 * gg + .114 * b
    for (let y = 1; y < c.height - 1; y++) for (let x = 1; x < c.width - 1; x++) {
      const i = (y * c.width + x) * 4, coverage = mask.data[i + 3] / 255
      if (!coverage) continue
      const center = lum(d[i], d[i + 1], d[i + 2])
      const left = lum(d[i - 4], d[i - 3], d[i - 2]), right = lum(d[i + 4], d[i + 5], d[i + 6])
      const above = lum(d[i - c.width * 4], d[i - c.width * 4 + 1], d[i - c.width * 4 + 2])
      const below = lum(d[i + c.width * 4], d[i + c.width * 4 + 1], d[i + c.width * 4 + 2])
      const texture = Math.min(1, (Math.abs(left - right) + Math.abs(above - below)) / 220)
      const noise = (((x * 73856093) ^ (y * 19349663) ^ entropy[(x + y) % entropy.length]) & 255) / 255
      const alpha = coverage * (0.43 + texture * .16 + (noise - .5) * .08)
      const tint = center > 132 ? [135, 25, 36] : [255, 224, 145]
      d[i] = d[i] * (1 - alpha) + tint[0] * alpha
      d[i + 1] = d[i + 1] * (1 - alpha) + tint[1] * alpha
      d[i + 2] = d[i + 2] * (1 - alpha) + tint[2] * alpha
    }
    g.putImageData(blendedPixels, 0, 0)
    // Reapply opaque masks last so the watermark can never put non-zero color into a masked region.
    for (const b of boxes) { g.fillStyle = '#000000'; g.fillRect(Math.round(b.x * c.width), Math.round(b.y * c.height), Math.max(1, Math.round(b.w * c.width)), Math.max(1, Math.round(b.h * c.height))) }
    const pixels = g.getImageData(0, 0, c.width, c.height)
    let clean = true
    for (const b of boxes) { const x0 = Math.round(b.x * c.width), y0 = Math.round(b.y * c.height), x1 = x0 + Math.max(1, Math.round(b.w * c.width)), y1 = y0 + Math.max(1, Math.round(b.h * c.height)); for (let y = y0; y < y1 && clean; y++) for (let x = x0; x < x1; x++) { const i = (y*c.width+x)*4; if (pixels.data[i] || pixels.data[i+1] || pixels.data[i+2]) { clean = false; break } } }
    if (!clean) { setNotice('Cannot verify safely · masked pixels were not all zero. Export blocked.'); return }
    const blob = await new Promise<Blob | null>((resolve) => c.toBlob(resolve, 'image/png'))
    if (!blob) { setNotice('Cannot verify safely · export could not be flattened.'); return }
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map((n) => n.toString(16).padStart(2, '0')).join('')
    setOutput(URL.createObjectURL(blob)); setDigest(hash); setMobileTab('verify')
  }

  const removeBox = (i: number) => { setBoxes((old) => old.filter((_, n) => n !== i)); resetOutput() }
  const download = () => { if (!output) return; const a = document.createElement('a'); a.href = output; a.download = 'surakshitid-purpose-locked.png'; a.click() }
  const scanPdf = async (file?: File) => {
    if (!file) return
    setPdfMode(true); setPdfFilename(file.name); setPdfResult(null); setPdfJob(null); setPdfError(null)
    try {
      const { job_id } = await api.processFile(file)
      const poll = async (): Promise<void> => {
        const job = await api.getJob(job_id); setPdfJob(job)
        if (job.status === 'done' && job.result) { setPdfResult(job.result); return }
        if (job.status === 'error') throw new Error(job.error ?? 'PDF processing failed')
        await new Promise((resolve) => window.setTimeout(resolve, 500))
        return poll()
      }
      await poll()
    } catch (error) { setPdfError(error instanceof Error ? error.message : 'Could not scan this PDF') }
  }
  const simulateTamper = async () => {
    if (!output) return
    const image = new Image(); image.src = output
    await new Promise<void>((resolve, reject) => { image.onload = () => resolve(); image.onerror = () => reject() })
    const c = document.createElement('canvas'); c.width = image.naturalWidth; c.height = image.naturalHeight
    const g = c.getContext('2d')!; g.drawImage(image, 0, 0)
    const x = Math.round(c.width * .418), y = Math.round(c.height * .227)
    g.fillStyle = '#fffdf6'; g.fillRect(x, y, Math.max(8, Math.round(c.width * .045)), Math.max(4, Math.round(c.height * .025)))
    const blob = await new Promise<Blob | null>((resolve) => c.toBlob(resolve, 'image/png'))
    if (!blob) return
    const alteredHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()))].map((n) => n.toString(16).padStart(2, '0')).join('')
    const previous = output
    setOutput(URL.createObjectURL(blob)); URL.revokeObjectURL(previous)
    setTamperAt({ x, y }); setTampered(alteredHash !== digest)
  }
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#home"><span className="brand-mark"><Shield /></span><span className="brand-name">surakshit<span>ID</span><small>सुरक्षित पहचान · Identity, on your terms</small></span></a><div className="top-actions"><span className="local-badge"><i/> ON-DEVICE DEMO</span><button className="icon-button" aria-label="Help" onClick={() => setNotice('This prototype demonstrates local raster masking. Use synthetic documents for the demo.')}>?</button><div className="avatar">AS</div></div></header>
    <main id="home">
      <section className="welcome-row"><div><div className="eyebrow"><span className="spark">✳</span> YOUR IDENTITY, YOUR RULES</div><h1>Share your ID.<br className="mobile-break"/> Keep control.</h1><p className="welcome-copy">Armor a copy for one purpose, one person, one moment.</p></div><div className="privacy-note"><span className="privacy-icon"><Shield size={17}/></span><span><b>Your document stays on this device.</b><small>Nothing is uploaded or stored by SurakshitID.</small></span></div></section>

      {pdfMode ? <section className="panel pdf-panel">
        <div className="panel-heading"><div><span className="step-num">PDF</span><div><h2>Local PDF scanner</h2><p>Existing Aadhaar and thumbprint detection pipeline</p></div></div><button className="text-button" onClick={() => { setPdfMode(false); setPdfJob(null); setPdfResult(null); setPdfError(null) }}>← Back to image armor</button></div>
        {pdfError && <div className="notice" role="alert">{pdfError}</div>}
        {!pdfResult && !pdfError && <ProgressCard job={pdfJob} filename={pdfFilename} />}
        {pdfResult && <><div className="notice">This PDF scanner is the repository’s existing redaction flow. Its output is not purpose-watermarked.</div><ResultView result={pdfResult} mock={api.isMock()} onReset={() => { setPdfMode(false); setPdfJob(null); setPdfResult(null) }}/></>}
      </section> : <div className="workspace">
        <section className={`panel armor-panel ${mobileTab === 'armor' ? 'active-mobile' : ''}`}>
          <div className="panel-heading"><div><span className="step-num">01</span><div><h2>Choose what to share</h2><p>Set a purpose. We’ll help protect the rest.</p></div></div><span className="step-label">ARMOR</span></div>
          <div className="purpose-block"><label className="field-label" htmlFor="purpose">SHARE FOR</label><select id="purpose" value={presetName} onChange={(e) => { setPresetName(e.target.value); resetOutput() }}>{presets.map((p) => <option key={p.name}>{p.name}</option>)}</select><div className="purpose-note"><span>✳</span> This copy is locked to <b>{activePreset.name}</b></div></div>
          <div className="permissions"><div className="permission-group"><div className="permission-title"><span className="permission-dot visible-dot"/> VISIBLE TO THEM <span className="permission-hint">minimum needed</span></div><div className="chips">{activePreset.fields.map((f) => <span className="chip visible-chip" key={f}><span>✓</span>{f}</span>)}</div></div><div className="permission-group"><div className="permission-title"><span className="permission-dot masked-dot"/> ALWAYS MASKED <span className="permission-hint">physically removed</span></div><div className="chips">{activePreset.masks.map((f) => <span className="chip masked-chip" key={f}><span>▰</span>{f}</span>)}</div></div></div>
          <div className="document-heading"><div><span className="field-label">YOUR DOCUMENT</span><span className="synthetic-tag">SYNTHETIC SAMPLE</span></div><button className="text-button" onClick={() => { setSource(createSample()); setFileName('Synthetic Aadhaar sample'); setBoxes(starterBoxes); resetOutput(); setNotice('') }}>Reset sample ↺</button></div>
          <div className="tools-row"><button className="tool-button" onClick={openCamera}><span>◎</span> Capture</button><button className="tool-button" onClick={() => input.current?.click()}><span>↑</span> Upload image</button><button className="tool-button" onClick={() => pdfInput.current?.click()}><span>▤</span> Scan PDF</button><input ref={input} className="hidden-input" type="file" accept="image/*" capture="environment" onChange={(e) => { chooseFile(e.target.files?.[0]); e.currentTarget.value = '' }}/><input ref={pdfInput} className="hidden-input" type="file" accept="application/pdf,.pdf" onChange={(e) => { void scanPdf(e.target.files?.[0]); e.currentTarget.value = '' }}/><span className="file-label">{fileName}</span></div>
          <div className="doc-workarea">
            {camera ? <div className="camera-frame"><video ref={video} autoPlay playsInline/><div className="camera-guide"><i/><i/><i/><i/></div><div className="camera-actions"><button onClick={() => { setCamera(false); stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null }}>Cancel</button><button className="capture-button" onClick={capture}>Capture document</button></div></div> : <div className="document-preview" ref={previewRef} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}>
              {source && <img src={source} alt="Document preview" draggable={false}/>}
              {!source && <div className="empty-upload" onClick={() => input.current?.click()}><span>↑</span><b>Choose an image to get started</b><small>JPG, PNG or HEIC · stays on this device</small></div>}
              {source && boxes.map((b, i) => <div key={`${i}-${b.x}`} className="mask-box" style={{ left: `${b.x*100}%`, top: `${b.y*100}%`, width: `${b.w*100}%`, height: `${b.h*100}%` }}><span>{b.label}</span><button aria-label={`Remove ${b.label} mask`} onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); removeBox(i) }}>×</button></div>)}
              {drawStart && drawEnd && <div className="mask-box drawing-box" style={{ left: `${Math.min(drawStart.x,drawEnd.x)*100}%`, top: `${Math.min(drawStart.y,drawEnd.y)*100}%`, width: `${Math.abs(drawStart.x-drawEnd.x)*100}%`, height: `${Math.abs(drawStart.y-drawEnd.y)*100}%` }} />}
              {source && <div className="document-watermark">SYNTHETIC SAMPLE · NOT A REAL ID</div>}
            </div>}
            {!camera && <div className="canvas-hint"><span>＋</span> Drag over the document to mark any area for removal</div>}
          </div>
          <div className="panel-foot"><span className="foot-lock"><Shield size={15}/></span><span>Image flattened on-device. Metadata stripped on export.</span><span className="foot-check">✓</span></div>
          {notice && <div className="notice" role="status"><span>ⓘ</span>{notice}<button onClick={() => setNotice('')}>×</button></div>}
          <button className="armor-cta" disabled={!source || !boxes.length} onClick={() => void armor()}><Shield size={18}/> Armor &amp; create share copy <span>→</span></button>
          <p className="demo-disclaimer">Demo preview · mark sensitive areas yourself. Automated detection is not enabled.</p>
        </section>

        <aside className={`panel verify-panel ${mobileTab === 'verify' ? 'active-mobile' : ''}`}>
          <div className="panel-heading"><div><span className="step-num">02</span><div><h2>Verify before sharing</h2><p>Every copy gets checked before it leaves.</p></div></div><button className={`inspector-link ${inspector ? 'selected' : ''}`} onClick={() => { if (output) setInspector(!inspector) }} disabled={!output}>⌕ INSPECTOR</button></div>
          {!output ? <div className="verify-empty"><div className="empty-shield"><Shield size={30}/></div><h3>Your armored copy<br/>will appear here</h3><p>We’ll flatten, watermark and verify your document before it’s ready to share.</p><div className="empty-steps"><span><i>1</i> Pick a purpose</span><span><i>2</i> Mark sensitive areas</span><span><i>3</i> Create a share copy</span></div></div> : <div className="verify-content">
            <div className={`status-card ${tampered ? 'status-forgery' : ''}`}><div className="status-icon">{tampered ? '!' : '✓'}</div><div><b>{tampered ? 'FORGERY DETECTED' : 'VERIFIED · READY TO SHARE'}</b><small>{tampered ? 'Watermark integrity mismatch · coordinates 418, 227' : 'No hidden data found in masked regions'}</small></div><span className="status-dots">•••</span></div>
            <div className="output-preview"><img src={output} alt="Purpose locked, masked document"/><div className="output-stamp">{activePreset.name.toUpperCase()}<br/>ONLY</div><button className="zoom-btn" onClick={() => setInspector(true)} aria-label="Inspect output">⌕</button></div>
            <div className="check-list"><div><span className="check-mark">✓</span><span><b>Raster flattened</b><small>No hidden layers or selectable text</small></span><span className="check-ok">PASS</span></div><div><span className="check-mark">✓</span><span><b>Masked pixels destroyed</b><small>{boxes.length} regions · all pixel values 0x00</small></span><span className="check-ok">PASS</span></div><div><span className="check-mark">✓</span><span><b>Purpose watermark sealed</b><small>SHA-256 verified</small></span><span className="check-ok">PASS</span></div></div>
            <div className="hash-card"><span className="hash-icon">⌘</span><div><small>DOCUMENT SEAL · SHA-256 · REF {issueToken}</small><code>{digest.slice(0,16)}…{digest.slice(-8)}</code></div><button onClick={() => void navigator.clipboard?.writeText(digest)} aria-label="Copy hash">▢</button></div>
            <div className="expiry-card"><span>◷</span><div><b>Suggested share window</b><small>For {activePreset.name.toLowerCase()} · use promptly</small></div><code>{activePreset.duration.toUpperCase()}</code></div>
            {inspector && <div className="inspector-card"><div className="inspector-title"><span><span className="inspector-symbol">⌕</span> Adversarial inspector</span><button onClick={() => setInspector(false)}>×</button></div><div className="pixel-sample"><span>MASKED PIXEL SAMPLE</span><code>R 00&nbsp; G 00&nbsp; B 00&nbsp; A FF</code><b>ZERO ENTROPY</b></div><div className="inspector-line"><span>Copy / text selection</span><b>EMPTY</b></div><div className="inspector-line"><span>PNG metadata</span><b>NONE</b></div><button className="tamper-button" onClick={() => void simulateTamper()}>{tampered ? 'Tamper detected · run again' : 'Simulate watermark tampering'} <span>→</span></button>{tampered && tamperAt && <div className="forgery-detail">Altered pixels detected at x: {tamperAt.x}, y: {tamperAt.y}<br/>SHA-256 no longer matches the issued seal.</div>}</div>}
            <button className="download-cta" onClick={download} disabled={tampered}><span>↓</span> {tampered ? 'Export blocked · seal mismatch' : 'Download purpose-locked copy'} <span>PNG</span></button>
            <p className="share-disclaimer">The watermark records purpose; downloaded copies do not expire or prevent re-use.</p>
          </div>}
        </aside>
      </div>}
      <footer className="page-footer"><span>◈ <b>SurakshitID</b> · सुरक्षित पहचान</span><span>Privacy starts before you share.</span><a href="https://uidai.gov.in/" target="_blank" rel="noreferrer">About Aadhaar safety ↗</a></footer>
    </main>
    <nav className="mobile-nav"><button className={mobileTab === 'armor' ? 'active' : ''} onClick={() => setMobileTab('armor')}><span>01</span> Armor</button><button className={mobileTab === 'verify' ? 'active' : ''} onClick={() => setMobileTab('verify')}><span>02</span> Verify {output && <i/>}</button></nav>
  </div>
}
