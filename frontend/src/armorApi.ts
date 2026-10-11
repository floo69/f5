import { isMock } from './api'
import mockPresets from './mock/armor_presets.json'
import mockResultJson from './mock/armor_result.json'
import mockInspectJson from './mock/armor_inspect.json'
import mockVerifyJson from './mock/armor_verify.json'
import mockCopiesJson from './mock/armor_copies.json'
import mockStory from './mock/armor_agent_story.json'

// ---- Types mirroring docs/ARMOR_CONTRACT.md ----
export type PresetKey = 'hotel' | 'xerox' | 'sim' | 'rental' | 'school' | 'bank_loan'
export interface Preset {
  key: PresetKey
  label: string
  masks: string[]
  keeps: string[]
  default_days: number
  max_days: number
  not_valid_for: string[]
}
export interface VoiceIntent {
  ok: boolean
  preset: PresetKey | null
  recipient: string | null
  valid_days: number | null
  document: 'aadhaar' | 'pan' | 'any'
  missing: string[]
  confirmation: string
  parse_ms: number
}
export type Decision = 'ARMOR_AND_ISSUE' | 'INSUFFICIENT_PURPOSE' | 'BLOCK_FOR_REVIEW'
export type FindingType =
  | 'AADHAAR' | 'VID' | 'MASKED_AADHAAR' | 'PAN' | 'QR' | 'BARCODE' | 'FACE' | 'FINGERPRINT' | 'DOB' | 'NUMBER'
  | 'ADDRESS'
export interface IdFinding {
  type: FindingType
  bbox_px: [number, number, number, number]
  action: 'MASK' | 'MASK_PARTIAL' | 'KEEP'
  masked_px: number[][]
  value_masked: string | null
  confidence: number
  source: string
}
export interface Step {
  key: string
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
  ms: number | null
}
export interface Badge {
  v: 1
  armor_id: string
  preset: PresetKey
  recipient: string
  purpose: string
  issued_at: string
  expires_at: string
  width: number
  height: number
  tile_px: number
  sha256: string
  tiles_root: string
  prev_hash: string
  block_hash: string
  ledger_index: number
  public_key: string
  signature: string
}
export interface ArmorResult {
  armor_id: string
  decision: Decision
  reasons: string[]
  decision_us: number
  preset: Preset
  recipient: string
  issued_at: string
  expires_at: string
  watermark_text: string
  preprocess: {
    doc_kind: 'id_card' | 'a4_page' | 'unknown'
    quad_found: boolean
    rotation_deg: number
    blur_score: number
    blur_ok: boolean
    glare_fraction: number
    shadow_corrected: boolean
    metadata_removed: string[]
    width: number
    height: number
    dpi: number
  }
  ocr_quality: number
  /** v2.1: unclear photo, so extra details were hidden */
  careful?: boolean
  careful_reason?: string
  findings: IdFinding[]
  masks_px: number[][]
  verification: { status: 'pass' | 'fail' | 'skipped'; checks: { name: string; ok: boolean; detail: string }[] }
  badge: Badge | null
  timings_ms: Record<string, number>
}
export interface ArmorJob {
  job_id: string
  status: 'queued' | 'processing' | 'done' | 'error'
  error: string | null
  steps: Step[]
  result: ArmorResult | null
}
export interface Inspection {
  masks: {
    bbox_px: number[]
    pixels: number
    min: number
    max: number
    unique_values: number
    entropy_bits: number
    hex_sample: string
  }[]
  pdf: {
    text_chars: number
    text_sample: string
    metadata: Record<string, string>
    images: number
    annotations: number
    pages: number
  }
  png: { chunks: string[]; exif: boolean }
  brightened_mask_max: number
}
export interface VerifyReport {
  status: 'AUTHENTIC' | 'FORGERY_DETECTED' | 'EXPIRED' | 'UNKNOWN_BADGE' | 'NO_BADGE' | 'REVOKED'
  armor_id: string | null
  purpose: string | null
  recipient: string | null
  expires_at: string | null
  signature_ok: boolean
  width: number
  height: number
  tile_px: number
  altered_regions: number[][]
  altered_tiles: number
  total_tiles: number
  detail: string
}
export interface Copy {
  armor_id: string
  preset: PresetKey
  preset_label: string
  recipient: string
  purpose: string
  issued_at: string
  expires_at: string
  status: 'active' | 'expired' | 'revoked'
  revoked_at: string | null
}
export type AttackKind = 'erase_watermark' | 'swap_photo' | 'unmask' | 'crop'
export interface AttackResponse {
  attack_id: string
  image_url: string
  verify: VerifyReport
}
export interface IdSample {
  name: string
  label: string
  kind: string
}
export interface ArmorParams {
  file: Blob
  filename: string
  preset: PresetKey
  recipient: string
  valid_days: number
  source: 'camera' | 'upload'
}

// ---- Mock mode (shares the ?mock=1 / auto-fallback switch from api.ts) ----
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const MOCK_W = 1011
const MOCK_H = 638
const STEP_MS = 380
const STEP_DEFS: [string, string][] = [
  ['capture', 'Capture'], ['preprocess', 'Preprocess'], ['detect', 'Detect'], ['decide', 'Decide'],
  ['destroy', 'Destroy'], ['watermark', 'Watermark'], ['verify', 'Verify'], ['seal', 'Seal'],
]
const MOCK_SAMPLES: IdSample[] = [
  { name: 'aadhaar_clear', label: 'Aadhaar (clear)', kind: 'aadhaar' },
  { name: 'pan_card', label: 'PAN card', kind: 'pan' },
  { name: 'aadhaar_blurry', label: 'Aadhaar (blurry)', kind: 'aadhaar' },
]

const svgUrl = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`

/** Synthetic placeholder card (no real photos). */
function placeholderSvg(kind: 'input' | 'before' | 'after' | 'tampered', masks: number[][], regions: number[][] = []): string {
  const tamper = kind === 'tampered'
  const rects = masks
    .map((m) =>
      kind === 'before'
        ? `<rect x="${m[0]}" y="${m[1]}" width="${m[2] - m[0]}" height="${m[3] - m[1]}" fill="url(#px)" stroke="#dc2626" stroke-width="3"/>`
        : kind === 'input'
          ? ''
          : `<rect x="${m[0]}" y="${m[1]}" width="${m[2] - m[0]}" height="${m[3] - m[1]}" fill="#000"/>`,
    )
    .join('')
  const reg = regions
    .map((r) => `<rect x="${r[0]}" y="${r[1]}" width="${r[2] - r[0]}" height="${r[3] - r[1]}" fill="#f59e0b" opacity=".55"/>`)
    .join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${MOCK_W} ${MOCK_H}" width="${MOCK_W}" height="${MOCK_H}">
<defs><pattern id="px" width="16" height="16" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#555"/><rect x="8" y="8" width="8" height="8" fill="#555"/><rect x="8" width="8" height="8" fill="#aaa"/><rect y="8" width="8" height="8" fill="#aaa"/></pattern></defs>
<rect width="100%" height="100%" fill="#f1f5f9"/><rect x="0" y="0" width="${MOCK_W}" height="90" fill="#0f766e"/>
<text x="40" y="58" font-family="sans-serif" font-size="34" fill="#fff">SYNTHETIC ID – NOT A REAL DOCUMENT</text>
<rect x="50" y="150" width="210" height="250" rx="8" fill="#94a3b8"/><circle cx="155" cy="240" r="48" fill="#cbd5e1"/>
<text x="300" y="260" font-family="sans-serif" font-size="34" fill="#0f172a">ASHA SAMPLE KUMARI</text>
<text x="300" y="330" font-family="sans-serif" font-size="30" fill="#334155">DOB: 01/01/1990</text>
<text x="300" y="505" font-family="monospace" font-size="42" fill="#0f172a">${kind === 'input' ? '2345 6789 0124' : 'XXXX XXXX 0124'}</text>
<rect x="790" y="60" width="170" height="170" fill="#475569"/>
${kind === 'input' ? '' : rects}${reg}
${kind === 'input' ? '' : `<text x="40" y="610" font-family="sans-serif" font-size="18" fill="#b91c1c">${tamper ? 'TAMPERED COPY (mock)' : 'FOR PURPOSE ONLY (mock watermark)'}</text>`}
</svg>`
}

const mockJobs = new Map<string, { name: string; started: number; p: ArmorParams; recorded?: boolean }>()
let mockCopies: Copy[] | null = null
const copiesStore = (): Copy[] =>
  (mockCopies ??= mockCopiesJson.map((c) => {
    const issued = Date.now() - c.issued_ago_h * 3600000
    return {
      armor_id: c.armor_id, preset: c.preset as PresetKey, preset_label: c.preset_label, recipient: c.recipient,
      purpose: c.purpose, issued_at: new Date(issued).toISOString(),
      expires_at: new Date(issued + c.valid_h * 3600000).toISOString(),
      status: c.status as Copy['status'], revoked_at: c.status === 'revoked' ? new Date(issued + 3600000).toISOString() : null,
    }
  }))
const mockAttackRegions: Record<AttackKind, number[][]> = {
  erase_watermark: [[32, 580, 980, 625]],
  swap_photo: [[50, 150, 260, 400]],
  unmask: [[300, 470, 560, 520]],
  crop: [[0, 0, MOCK_W, MOCK_H]],
}

function mockResult(id: string, p: ArmorParams): ArmorResult {
  const base = structuredClone(mockResultJson) as unknown as ArmorResult
  const preset = (mockPresets as unknown as Preset[]).find((x) => x.key === p.preset) ?? base.preset
  const issued = new Date()
  const exp = new Date(issued.getTime() + p.valid_days * 86400000)
  base.armor_id = id
  base.preset = preset
  base.recipient = p.recipient
  base.issued_at = issued.toISOString()
  base.expires_at = exp.toISOString()
  base.watermark_text = watermarkText(preset, p.recipient, p.valid_days, issued)
  const blur = p.filename.includes('blur')
  const bad = p.recipient.trim().length < 3 || p.valid_days < 1 || p.valid_days > preset.max_days
  if (blur) {
    base.decision = 'BLOCK_FOR_REVIEW'
    base.reasons = ['Blur score 41 is below the threshold (80)', 'OCR quality 0.38 is too low to prove no Aadhaar digits remain']
    base.preprocess.blur_score = 41
    base.preprocess.blur_ok = false
    base.ocr_quality = 0.38
    base.verification = { status: 'skipped', checks: [] }
    base.badge = null
  } else if (bad) {
    base.decision = 'INSUFFICIENT_PURPOSE'
    base.reasons = [
      p.recipient.trim().length < 3 ? 'Recipient must be at least 3 characters' : `Validity must be between 1 and ${preset.max_days} days`,
    ]
    base.badge = null
  } else if (base.badge) {
    base.badge.armor_id = id
    base.badge.preset = preset.key
    base.badge.recipient = p.recipient
    base.badge.purpose = `${preset.label.toUpperCase()} ONLY`
    base.badge.issued_at = base.issued_at
    base.badge.expires_at = base.expires_at
  }
  return base
}

function mockJobState(id: string): ArmorJob {
  const m = mockJobs.get(id)
  if (!m) throw new Error('unknown mock job')
  const t = Date.now() - m.started
  const idx = Math.floor(t / STEP_MS)
  const done = idx >= STEP_DEFS.length
  const res = mockResult(id, m.p)
  const steps: Step[] = STEP_DEFS.map(([key, label], i) => ({
    key,
    label,
    status: i < idx ? 'done' : i === idx ? 'running' : 'pending',
    ms: i < idx ? (res.timings_ms[key] ?? 1) : null,
  }))
  if (done && !m.recorded && res.decision === 'ARMOR_AND_ISSUE') {
    m.recorded = true
    copiesStore().unshift({
      armor_id: id, preset: res.preset.key, preset_label: res.preset.label, recipient: res.recipient,
      purpose: `${res.preset.label.toUpperCase()} ONLY`, issued_at: res.issued_at, expires_at: res.expires_at,
      status: 'active', revoked_at: null,
    })
  }
  return { job_id: id, status: done ? 'done' : 'processing', error: null, steps, result: done ? res : null }
}

export function watermarkText(preset: Preset, recipient: string, days: number, from = new Date()): string {
  const fmt = (d: Date) =>
    d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase()
  const to = new Date(from.getTime() + days * 86400000)
  return `FOR ${recipient.trim().toUpperCase() || '…'} ${preset.label.toUpperCase()} ONLY · ${fmt(from)} – ${fmt(to)} · NOT VALID FOR ${preset.not_valid_for.join(', ')}`
}

function mockVoice(text: string): VoiceIntent {
  const t0 = performance.now()
  const lower = text.toLowerCase()
  const table: [RegExp, PresetKey][] = [
    [/hotel|check.?in/, 'hotel'], [/xerox|print|photocopy/, 'xerox'], [/\bsim\b|telecom|mobile/, 'sim'],
    [/rent|landlord|tenant/, 'rental'], [/school|admission/, 'school'], [/loan|bank/, 'bank_loan'],
  ]
  const preset = table.find(([r]) => r.test(lower))?.[1] ?? null
  const dm = lower.match(/(\d+)\s*days?/)
  const rm = text.match(/(?:with|to)\s+(.+?)(?=\s+for\s+\d|\s+for\s+(?:hotel|check)|\s+and\b|,\s*\d|\.|$)/i)
  const recipient = rm ? rm[1].trim() : null
  const days = dm ? Number(dm[1]) : null
  const missing = [preset ? '' : 'preset', recipient ? '' : 'recipient'].filter(Boolean)
  const doc: VoiceIntent['document'] = /pan/.test(lower) ? 'pan' : /aadhaar|aadhar/.test(lower) ? 'aadhaar' : 'any'
  const label = (mockPresets as unknown as Preset[]).find((p) => p.key === preset)?.label
  return {
    ok: missing.length === 0,
    preset,
    recipient,
    valid_days: days,
    document: doc,
    missing,
    confirmation: missing.length
      ? `I still need the ${missing.join(' and ')}.`
      : `Armoring ${doc === 'any' ? 'your ID' : doc} for ${recipient}, ${label}, valid ${days ?? 'default'} days.`,
    parse_ms: Math.round((performance.now() - t0) * 100) / 100,
  }
}

// ---- Real client ----
async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export async function listPresets(): Promise<Preset[]> {
  if (isMock()) return structuredClone(mockPresets) as unknown as Preset[]
  return json<Preset[]>(await fetch('/api/presets'))
}

export async function listIdSamples(): Promise<IdSample[]> {
  if (isMock()) return MOCK_SAMPLES
  return json<IdSample[]>(await fetch('/api/id-samples'))
}

// Sample originals never reach the browser (a KYC sample holds a synthetic thumbprint): the
// File below is only the pixelated preview, tagged so startArmor armors the original server-side.
const sampleOf = new WeakMap<Blob, string>()

/** Fetches a synthetic sample's (pixelated) preview as a File for the capture thumbnail. */
export async function getIdSampleFile(name: string): Promise<File> {
  if (isMock()) {
    const blob = new Blob([placeholderSvg('input', [])], { type: 'image/svg+xml' })
    return new File([blob], `${name}.svg`, { type: 'image/svg+xml' })
  }
  const res = await fetch(`/api/id-samples/${encodeURIComponent(name)}.jpg`)
  if (!res.ok) throw new Error(`${res.status}: could not load sample`)
  const f = new File([await res.blob()], `${name}.jpg`, { type: 'image/jpeg' })
  sampleOf.set(f, name)
  return f
}

export async function parseVoice(text: string): Promise<VoiceIntent> {
  if (isMock()) {
    await sleep(60)
    return mockVoice(text)
  }
  return json<VoiceIntent>(
    await fetch('/api/voice/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  )
}

export async function startArmor(p: ArmorParams): Promise<{ job_id: string }> {
  if (isMock()) {
    const id = 'SKID-' + Math.random().toString(36).slice(2, 6).toUpperCase() + '-' + Math.random().toString(36).slice(2, 6).toUpperCase()
    mockJobs.set(id, { name: p.filename, started: Date.now(), p })
    await sleep(120)
    return { job_id: id }
  }
  const fd = new FormData()
  const sample = sampleOf.get(p.file)
  if (!sample) fd.append('file', p.file, p.filename)
  fd.append('preset', p.preset)
  fd.append('recipient', p.recipient)
  fd.append('valid_days', String(p.valid_days))
  fd.append('source', p.source)
  const url = sample ? `/api/id-samples/${encodeURIComponent(sample)}/armor` : '/api/armor'
  return json(await fetch(url, { method: 'POST', body: fd }))
}

export async function getArmorJob(id: string): Promise<ArmorJob> {
  if (isMock()) return mockJobState(id)
  return json<ArmorJob>(await fetch(`/api/armor/${id}`))
}

export function viewUrl(id: string, which: 'before' | 'after'): string {
  if (isMock()) {
    const masks = (mockResultJson as unknown as ArmorResult).masks_px
    return svgUrl(placeholderSvg(which, masks))
  }
  return `/api/armor/${id}/view.png?which=${which}`
}

export type DownloadKind = 'armored.png' | 'armored.pdf' | 'badge.json'
export function downloadUrl(id: string, kind: DownloadKind, result?: ArmorResult): string | null {
  if (isMock()) {
    if (kind === 'armored.png') return svgUrl(placeholderSvg('after', (mockResultJson as unknown as ArmorResult).masks_px))
    if (kind === 'badge.json' && result?.badge)
      return 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(result.badge, null, 2))
    return null // no PDF in demo mode
  }
  return `/api/armor/${id}/${kind}`
}

export async function getInspection(id: string): Promise<Inspection> {
  if (isMock()) {
    await sleep(150)
    return structuredClone(mockInspectJson) as unknown as Inspection
  }
  return json<Inspection>(await fetch(`/api/armor/${id}/inspect`))
}

/** Most recent attack in this session: the Agents tab can send it for forensic review. */
export let lastAttack: { id: string; kind: AttackKind } | null = null

export async function attack(id: string, kind: AttackKind): Promise<AttackResponse> {
  const res = await attackRaw(id, kind)
  lastAttack = { id: res.attack_id, kind }
  return res
}

async function attackRaw(id: string, kind: AttackKind): Promise<AttackResponse> {
  if (isMock()) {
    await sleep(500)
    const verify = structuredClone(mockVerifyJson) as unknown as VerifyReport
    verify.armor_id = id
    verify.altered_regions = mockAttackRegions[kind]
    verify.altered_tiles = kind === 'crop' ? 640 : 18
    verify.detail =
      kind === 'crop'
        ? 'Image size differs from the sealed badge; every tile is considered altered.'
        : `${verify.altered_tiles} of ${verify.total_tiles} tiles differ from the sealed hashes; signature itself is valid.`
    const masks = (mockResultJson as unknown as ArmorResult).masks_px
    return {
      attack_id: 'atk-' + Math.random().toString(36).slice(2, 8),
      image_url: svgUrl(placeholderSvg('tampered', masks)),
      verify,
    }
  }
  return json<AttackResponse>(
    await fetch(`/api/armor/${id}/attack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind }),
    }),
  )
}

export async function verifyFile(file: File): Promise<VerifyReport> {
  if (isMock()) {
    await sleep(700)
    const v = structuredClone(mockVerifyJson) as unknown as VerifyReport
    const n = file.name.toLowerCase()
    if (n.includes('expired')) return { ...v, status: 'EXPIRED', altered_regions: [], altered_tiles: 0, detail: 'Badge expired.' }
    if (n.includes('revoked')) return { ...v, status: 'REVOKED', altered_regions: [], altered_tiles: 0, detail: 'The owner withdrew this copy.' }
    if (n.includes('nobadge')) return { ...v, status: 'NO_BADGE', armor_id: null, purpose: null, recipient: null, altered_regions: [], altered_tiles: 0, signature_ok: false, detail: 'No SurakshitID badge strip found.' }
    if (n.includes('unknown')) return { ...v, status: 'UNKNOWN_BADGE', altered_regions: [], altered_tiles: 0, signature_ok: false, detail: 'Badge not issued by this device ledger.' }
    if (n.includes('forged') || n.includes('tamper')) return v
    return { ...v, status: 'AUTHENTIC', altered_regions: [], altered_tiles: 0, detail: 'All tiles match the sealed hashes.' }
  }
  const fd = new FormData()
  fd.append('file', file)
  return json<VerifyReport>(await fetch('/api/verify', { method: 'POST', body: fd }))
}

// ---- My copies (v2.1) ----
export async function listCopies(): Promise<Copy[]> {
  if (isMock()) {
    await sleep(120)
    const now = Date.now()
    return copiesStore().map((c) =>
      c.status === 'active' && new Date(c.expires_at).getTime() < now ? { ...c, status: 'expired' as const } : { ...c },
    )
  }
  return json<Copy[]>(await fetch('/api/copies'))
}

export async function revokeCopy(armorId: string): Promise<Copy> {
  if (isMock()) {
    await sleep(300)
    const c = copiesStore().find((x) => x.armor_id === armorId)
    if (!c) throw new Error('unknown copy')
    c.status = 'revoked'
    c.revoked_at = new Date().toISOString()
    return { ...c }
  }
  return json<Copy>(await fetch(`/api/copies/${encodeURIComponent(armorId)}/revoke`, { method: 'POST' }))
}

// ---- Agents (SSE timeline) ----
export type AgentStep = 'scan' | 'found' | 'lock' | 'review' | 'notice' | 'done'
export interface AgentFinding {
  page_url: string
  kinds: string[]
  masked: string[]
  /** server image of the leaked document, sensitive parts already blacked out */
  thumb_url: string
}
export interface AgentDone {
  summary?: string
  exposed_count?: number
  risk?: 'high' | 'medium' | 'low' | 'none'
  notice?: string
  escalated?: boolean
  cost_usd?: number
  mode?: string
  error?: string
}
export interface AgentEvent {
  agent: string
  type: string
  /** one plain sentence for the UI */
  say?: string
  step?: AgentStep
  finding?: AgentFinding
  attack_type?: string
  text?: string
  tool?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown> | null
  result?: Record<string, unknown>
  decision?: string
  replayed?: boolean
  deterministic?: boolean
  [k: string]: unknown
}
export interface AgentConfig {
  mode: 'live' | 'replay' | 'off'
  provider: string
  budget_usd: number
  allowlist: string[]
  models: Record<string, string>
}

export async function agentConfig(): Promise<AgentConfig> {
  if (isMock())
    return { mode: 'off', provider: 'anthropic', budget_usd: 0.5, allowlist: ['localhost:8100'],
      models: { orchestrator: 'claude-sonnet-5-5', auditor: 'claude-sonnet-5-5', reviewer: 'claude-sonnet-5-5', notice: 'claude-haiku-5-5' } }
  return json<AgentConfig>(await fetch('/api/agents/config'))
}

const thumbSvg = (n: number) =>
  svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" width="320" height="200"><rect width="320" height="200" fill="#f1f5f9"/><rect width="320" height="26" fill="#0f766e"/><text x="12" y="18" font-family="sans-serif" font-size="11" fill="#fff">SYNTHETIC SAMPLE ${n}</text><rect x="16" y="46" width="64" height="84" rx="6" fill="#cbd5e1"/><rect x="96" y="52" width="130" height="10" rx="5" fill="#94a3b8"/><rect x="96" y="74" width="90" height="10" rx="5" fill="#cbd5e1"/><rect x="96" y="150" width="150" height="20" fill="#000"/><rect x="246" y="46" width="58" height="58" fill="#000"/></svg>`)

function mockEvents(p: { case: 'audit' } | { case: 'forgery'; attack_id: string }): AgentEvent[] {
  const src = (p.case === 'audit' ? mockStory.audit : mockStory.forgery) as AgentEvent[]
  return src.map((e) => {
    const ev = structuredClone(e)
    if (ev.finding) ev.finding.thumb_url = thumbSvg(Number(ev.finding.thumb_url.replace(/\D/g, '')) || 1)
    return ev
  })
}

/** Streams an agent case; returns a function that stops it. */
export function runAgents(
  params: { case: 'audit' } | { case: 'forgery'; attack_id: string },
  onEvent: (e: AgentEvent) => void,
  onError: (msg: string) => void,
): () => void {
  if (isMock()) {
    const evs = mockEvents(params)
    let i = 0
    const t = window.setInterval(() => {
      onEvent(evs[i++])
      if (i >= evs.length) window.clearInterval(t)
    }, 1100)
    return () => window.clearInterval(t)
  }
  const q = new URLSearchParams(params as Record<string, string>)
  const es = new EventSource(`/api/agents/run?${q}`)
  const handle = (m: MessageEvent) => {
    const ev = JSON.parse(m.data) as AgentEvent
    onEvent(ev)
    if (ev.type === 'done') es.close()
  }
  for (const t of ['start', 'tool', 'text', 'result', 'note', 'blocked', 'handover', 'escalation', 'refusal', 'review', 'found', 'notice', 'error', 'done'])
    es.addEventListener(t, handle as EventListener)
  es.onmessage = handle
  es.onerror = () => {
    es.close()
    onError('Agent stream closed')
  }
  return () => es.close()
}
