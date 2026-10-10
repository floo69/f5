import { useState } from 'react'
import { pageUrl, type Finding, type PageResult } from '../api'

interface Props {
  jobId: string
  page: PageResult
  view: 'before' | 'after'
  boxes: boolean
  mock: boolean
  dpi?: number
  interactive?: boolean
}

const label = (t: Finding['type']) =>
  ({ FINGERPRINT: 'Thumbprint', AADHAAR: 'Aadhaar', VID: 'VID', MASKED_AADHAAR: 'Masked Aadhaar' })[t]

/** Grey A4 placeholder with synthetic text bars; fingerprints pixelated (before) or blacked (after). */
function Placeholder({ page, view }: { page: PageResult; view: 'before' | 'after' }) {
  const [w, h] = page.size_pt
  const bars = Array.from({ length: 26 }, (_, i) => i)
  const redacted = page.findings.filter((f) => f.redact)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 h-full w-full" role="img"
      aria-label={`Placeholder for page ${page.page + 1}, ${view}`}>
      <rect width={w} height={h} fill="#f1f5f9" />
      <text x={w / 2} y={52} textAnchor="middle" fontSize={15} fontWeight={600} fill="#94a3b8">SALE DEED</text>
      {page.text_layer &&
        bars.map((i) => (
          <rect key={i} x={72} y={86 + i * 21} width={(i * 53) % 90 > 70 ? 300 : 450 - ((i * 37) % 120)} height={6}
            rx={3} fill="#cbd5e1" />
        ))}
      {!page.text_layer && (
        <g opacity={0.8}>
          {bars.map((i) => (
            <rect key={i} x={72 + (i % 3)} y={86 + i * 21} width={420 - ((i * 41) % 140)} height={6} rx={3} fill="#cbd5e1" />
          ))}
          <text x={w / 2} y={h / 2} textAnchor="middle" fontSize={20} fill="#94a3b8" transform={`rotate(-8 ${w / 2} ${h / 2})`}>
            scanned page
          </text>
        </g>
      )}
      {redacted.map((f, i) => {
        const [x0, y0, x1, y1] = f.bbox_pt
        if (view === 'after') return <rect key={i} x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill="#0f172a" />
        if (f.type !== 'FINGERPRINT') return <rect key={i} x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill="#94a3b8" />
        const cells: React.ReactNode[] = []
        const s = 8
        for (let x = x0, c = 0; x < x1; x += s, c++)
          for (let y = y0, r = 0; y < y1; y += s, r++)
            cells.push(<rect key={`${c}-${r}`} x={x} y={y} width={s} height={s} fill={`hsl(215 16% ${30 + ((c * 7 + r * 13) % 40)}%)`} />)
        return <g key={i}>{cells}</g>
      })}
      {view === 'before' &&
        page.findings.filter((f) => !f.redact).map((f, i) => (
          <rect key={`m${i}`} x={f.bbox_pt[0]} y={f.bbox_pt[1]} width={f.bbox_pt[2] - f.bbox_pt[0]}
            height={f.bbox_pt[3] - f.bbox_pt[1]} fill="#94a3b8" opacity={0.7} />
        ))}
    </svg>
  )
}

export default function PageImage({ jobId, page, view, boxes, mock, dpi = 100, interactive = true }: Props) {
  const [w, h] = page.size_pt
  const [hover, setHover] = useState<number | null>(null)
  const [broken, setBroken] = useState(false)
  const showPlaceholder = mock || broken
  const f = hover !== null ? page.findings[hover] : null

  return (
    <div className="relative w-full overflow-hidden rounded-md bg-slate-100 shadow-sm ring-1 ring-slate-300"
      style={{ aspectRatio: `${w} / ${h}` }}>
      {showPlaceholder ? (
        <Placeholder page={page} view={view} />
      ) : (
        <img src={pageUrl(jobId, page.page, view, dpi)} alt={`Page ${page.page + 1}, ${view === 'before' ? 'original with thumbprints pixelated' : 'after redaction'}`}
          className="absolute inset-0 h-full w-full" onError={() => setBroken(true)} />
      )}
      {boxes && (
        <svg viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 h-full w-full" aria-hidden={!interactive}>
          {page.findings.map((fi, i) => {
            const [x0, y0, x1, y1] = fi.bbox_pt
            const ok = !fi.redact
            return (
              <rect key={i} x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx={2}
                fill={ok ? 'rgba(16,185,129,0.10)' : 'rgba(220,38,38,0.12)'}
                stroke={ok ? '#059669' : '#dc2626'} strokeWidth={hover === i ? 3 : 1.8}
                strokeDasharray={ok ? '6 4' : undefined}
                style={{ pointerEvents: interactive ? 'all' : 'none' }}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            )
          })}
        </svg>
      )}
      {f && (
        <div className="pointer-events-none absolute z-10 w-max max-w-[16rem] -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs text-white shadow-lg"
          style={{
            left: `${(((f.bbox_pt[0] + f.bbox_pt[2]) / 2) / w) * 100}%`,
            top: `${(f.bbox_pt[3] / h) * 100 + 1.5}%`,
          }}>
          <div className="font-semibold">{label(f.type)}{f.redact ? '' : ' (already compliant)'}</div>
          <div className="text-slate-300">confidence {(f.confidence * 100).toFixed(0)}% · source {f.source}</div>
          {f.value_masked && <div className="mt-0.5 font-mono">{f.value_masked}</div>}
        </div>
      )}
    </div>
  )
}
