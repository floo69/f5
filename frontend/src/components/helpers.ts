import type { Decision, FindingType, PageResult } from '../api'
import type { PresetKey } from '../armorApi'

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
  camera: 'M4 8h3l2-3h6l2 3h3v11H4z M12 10.500a3.500 3.500 0 100 7 3.500 3.500 0 000-7z',
  mic: 'M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z M6 11a6 6 0 0012 0 M12 17v4 M9 21h6',
  bolt: 'M13 3L5 14h6l-1 7 8-11h-6z',
  x: 'M6 6l12 12 M18 6L6 18',
  share: 'M12 15V3 M7 8l5-5 5 5 M5 12v8h14v-8',
  inspect: 'M10.500 4a6.500 6.500 0 100 13 6.500 6.500 0 000-13z M15.500 15.500L21 21',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 9.500a2.500 2.500 0 100 5 2.500 2.500 0 000-5z',
}

export const ICONS2 = {
  bed: 'M3 18V6 M3 14h18v4 M21 14v-2a3 3 0 00-3-3h-7v5 M7 11.500a1.500 1.500 0 100-3 1.500 1.500 0 000 3z',
  print: 'M7 9V3h10v6 M7 17H4v-7h16v7h-3 M7 14h10v7H7z',
  phone: 'M8 3h8a1 1 0 011 1v16a1 1 0 01-1 1H8a1 1 0 01-1-1V4a1 1 0 011-1z M11 18h2',
  home: 'M4 11l8-7 8 7 M6 10v10h12V10 M10 20v-6h4v6',
  school: 'M2 9l10-5 10 5-10 5z M6 11.500V16c0 1.500 2.700 3 6 3s6-1.500 6-3v-4.500',
  bank: 'M3 10l9-6 9 6 M5 10v8 M9.500 10v8 M14.500 10v8 M19 10v8 M3 21h18',
  list: 'M8 6h12 M8 12h12 M8 18h12 M4 6h.01 M4 12h.01 M4 18h.01',
  scan: 'M4 8V5a1 1 0 011-1h3 M16 4h3a1 1 0 011 1v3 M20 16v3a1 1 0 01-1 1h-3 M8 20H5a1 1 0 01-1-1v-3 M4 12h16',
  bell: 'M6 16V11a6 6 0 0112 0v5l2 2H4z M10 21h4',
  building: 'M5 21V4h9v17 M14 9h5v12 M8 8h3 M8 12h3 M8 16h3 M3 21h18',
  qr: 'M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h2v2h-2z M18 14h2v6h-4 M14 18v2',
  hand: 'M9 11V5a1.500 1.500 0 013 0v5 M12 10V4a1.500 1.500 0 013 0v7 M15 11V6a1.500 1.500 0 013 0v8c0 4-3 7-6 7s-5-2-6-5l-2-4a1.500 1.500 0 012.500-1.500L9 14',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8z M4 21c0-4 3.500-6 8-6s8 2 8 6',
  note: 'M6 3h9l4 4v14H6z M9 12h7 M9 16h7',
  info: 'M12 21a9 9 0 100-18 9 9 0 000 18z M12 11v5 M12 7.500v.01',
  chevron: 'M6 9l6 6 6-6',
  ban: 'M12 21a9 9 0 100-18 9 9 0 000 18z M5.600 5.600l12.800 12.800',
  clock: 'M12 21a9 9 0 100-18 9 9 0 000 18z M12 7v5l3 2',
  sparkle: 'M12 3l1.800 5.200L19 10l-5.200 1.800L12 17l-1.800-5.200L5 10l5.200-1.800z',
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

export const PRESET_INFO: Record<PresetKey, { icon: string; line: string }> = {
  hotel: { icon: ICONS2.bed, line: 'Hides most of your Aadhaar number and QR' },
  xerox: { icon: ICONS2.print, line: 'Hides every number. Valid for one day' },
  sim: { icon: ICONS2.phone, line: 'Keeps what a SIM shop needs, hides the rest' },
  rental: { icon: ICONS2.home, line: 'Shares name and address, hides numbers' },
  school: { icon: ICONS2.school, line: 'Keeps name, birth date and address' },
  bank_loan: { icon: ICONS2.bank, line: 'Shows more for lenders, thumbprints still removed' },
}

