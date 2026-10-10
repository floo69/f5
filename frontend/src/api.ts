import resultBlocked from './mock/result.json'
import resultClean from './mock/result_clean.json'
import resultFail from './mock/result_fail.json'

// ---- Types mirroring docs/API_CONTRACT.md ----
export type FindingType = 'FINGERPRINT' | 'AADHAAR' | 'VID' | 'MASKED_AADHAAR'
export type Decision = 'PUBLISH' | 'REDACT_AND_PUBLISH' | 'BLOCK_FOR_REVIEW'

export interface Finding {
  type: FindingType
  page: number
  bbox_pt: [number, number, number, number]
  confidence: number
  source: 'textlayer' | 'ocr' | 'classical' | 'onnx' | 'classical+onnx'
  value_masked: string | null
  redact: boolean
}

export interface PageResult {
  page: number
  size_pt: [number, number]
  text_layer: boolean
  ocr_quality: number
  decision: Decision
  reasons: string[]
  findings: Finding[]
  counts: Record<FindingType, number>
  timings_ms: Record<string, number>
  system_one?: { action?: string; confidence?: number; backend?: string; fallback?: boolean; latency_ms?: number }
}

export interface Problem {
  page: number
  type: string
  bbox_pt: number[]
  detail: string
}

export interface Result {
  doc_id: string
  sha256_in: string
  sha256_out: string
  page_count: number
  status: 'VERIFIED_CLEAN' | 'BLOCKED_FOR_REVIEW'
  pages: PageResult[]
  verification: { status: 'pass' | 'fail'; problems: Problem[] }
  timings_ms: Record<string, number>
  detector_versions: Record<string, string>
  detector_mode?: 'classical' | 'onnx' | 'fused'
  detector_status?: Record<string, unknown>
}

export interface RuntimeStatus {
  detector_mode: 'classical' | 'onnx' | 'fused'
  detector: { classical: { available: boolean; active: boolean }; onnx: { available: boolean; active: boolean; size_bytes?: number; quantization?: string } }
  offline_ready: boolean
  capabilities: { tesseract: boolean; onnxruntime: boolean }
}

export interface Job {
  job_id: string
  filename: string
  status: 'queued' | 'processing' | 'done' | 'error'
  error: string | null
  progress: { pages_done: number; pages_total: number }
  result: Result | null
}

export interface Sample {
  name: string
  mode: 'born_digital' | 'scanned'
}

// ---- Mock mode ----
const params = new URLSearchParams(window.location.search)
const mockParam = params.get('mock')
export const mockVariant: string | null = mockParam
let mock = mockParam !== null && mockParam !== '0'

export const isMock = () => mock
export const setMock = (v: boolean) => {
  mock = v
}

export function mockResult(variant: string | null = mockVariant): Result {
  const r = variant === 'clean' ? resultClean : variant === 'fail' ? resultFail : resultBlocked
  return structuredClone(r) as unknown as Result
}

const MOCK_SAMPLES: Sample[] = [
  { name: 'sale_deed_born_digital', mode: 'born_digital' },
  { name: 'sale_deed_scanned', mode: 'scanned' },
  { name: 'sale_deed_multipage', mode: 'born_digital' },
]

const mockJobs = new Map<string, { filename: string; started: number }>()
const MOCK_MS = 1800

function mockJob(id: string): Job {
  const m = mockJobs.get(id)
  if (!m) throw new Error('unknown mock job')
  const frac = Math.min(1, (Date.now() - m.started) / MOCK_MS)
  const total = 3
  const done = frac >= 1
  return {
    job_id: id,
    filename: m.filename,
    status: done ? 'done' : 'processing',
    error: null,
    progress: { pages_done: done ? total : Math.floor(frac * total), pages_total: total },
    result: done ? mockResult() : null,
  }
}

function startMock(filename: string): { job_id: string } {
  const id = 'mock-' + Math.random().toString(36).slice(2, 8)
  mockJobs.set(id, { filename, started: Date.now() })
  return { job_id: id }
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

/** Returns true if the backend is reachable. */
export async function checkHealth(): Promise<boolean> {
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), 2500)
    const res = await fetch('/api/health', { signal: ctrl.signal })
    clearTimeout(t)
    if (!res.ok) return false
    const body = await res.json()
    return body?.status === 'ok'
  } catch {
    return false
  }
}

export async function runtimeStatus(): Promise<RuntimeStatus> {
  return json<RuntimeStatus>(await fetch('/api/health'))
}

export async function listSamples(): Promise<Sample[]> {
  if (mock) return MOCK_SAMPLES
  return json<Sample[]>(await fetch('/api/samples'))
}

export async function processFile(file: File): Promise<{ job_id: string }> {
  if (mock) return startMock(file.name)
  const fd = new FormData()
  fd.append('file', file)
  return json(await fetch('/api/process', { method: 'POST', body: fd }))
}

export async function processSample(name: string): Promise<{ job_id: string }> {
  if (mock) return startMock(name + '.pdf')
  return json(await fetch(`/api/samples/${encodeURIComponent(name)}/process`, { method: 'POST' }))
}

export async function getJob(id: string): Promise<Job> {
  if (mock) return mockJob(id)
  return json<Job>(await fetch(`/api/jobs/${id}`))
}

export const fileUrl = (id: string, kind: 'redacted' | 'certificate' | 'certificate.pdf') =>
  `/api/files/${id}/${kind}`

export const pageUrl = (id: string, n: number, view: 'before' | 'after', dpi = 100) =>
  // outlines=0: the UI draws its own (toggleable) finding boxes over the image
  `/api/files/${id}/page/${n}.png?view=${view}&dpi=${dpi}&outlines=0`
