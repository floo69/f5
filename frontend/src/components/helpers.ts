import type { Decision, FindingType, PageResult } from '../api'

export const DECISION_META: Record<Decision, { label: string; dot: string; chip: string }> = {
  PUBLISH: { label: 'Publish', dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-800 ring-emerald-200' },
  REDACT_AND_PUBLISH: {
    label: 'Redact & publish',
    dot: 'bg-amber-500',
    chip: 'bg-amber-50 text-amber-900 ring-amber-200',
  },
  BLOCK_FOR_REVIEW: { label: 'Block for review', dot: 'bg-red-500', chip: 'bg-red-50 text-red-800 ring-red-200' },
}

export const ICONS = {
  shield: 'M12 3l8 3v6c0 5-3.4 8.600-8 10-4.600-1.400-8-5-8-10V6z M8.500 12l2.500 2.500 4.500-5',
  lock: 'M6 11h12v9H6z M8.500 11V8a3.500 3.500 0 017 0v3',
  upload: 'M12 16V4 M7 9l5-5 5 5 M4 16v4h16v-4',
  file: 'M7 3h7l5 5v13H7z M14 3v5h5',
  download: 'M12 4v12 M7 11l5 5 5-5 M4 20h16',
  copy: 'M9 9h11v11H9z M5 15V4h11',
  check: 'M5 12.500l4.500 4.500L19 7',
  alert: 'M12 4l9 16H3z M12 10v4 M12 17.500v.01',
  refresh: 'M4 12a8 8 0 0114-5.300L20 9 M20 4v5h-5 M20 12a8 8 0 01-14 5.300L4 15 M4 20v-5h5',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9.500a2.500 2.500 0 100 5 2.500 2.500 0 000-5z',
}

export const shortHash = (h: string) => (h.length > 16 ? `${h.slice(0, 8)}…${h.slice(-6)}` : h)

export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`

export function totals(pages: PageResult[]) {
  const t: Record<FindingType, number> = { FINGERPRINT: 0, AADHAAR: 0, VID: 0, MASKED_AADHAAR: 0 }
  for (const p of pages) for (const k of Object.keys(t) as FindingType[]) t[k] += p.counts[k] ?? 0
  return t
}

export function countChips(counts: Record<FindingType, number>): string[] {
  const out: string[] = []
  if (counts.FINGERPRINT) out.push(plural(counts.FINGERPRINT, 'thumbprint'))
  if (counts.AADHAAR) out.push(`${counts.AADHAAR} Aadhaar`)
  if (counts.VID) out.push(plural(counts.VID, 'VID'))
  if (counts.MASKED_AADHAAR) out.push(`${counts.MASKED_AADHAAR} masked (OK)`)
  return out
}
