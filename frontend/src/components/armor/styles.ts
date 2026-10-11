export const btnBase =
  'inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold transition duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100'
export const btnPrimary = `${btnBase} bg-accent-700 text-white shadow-[0_6px_16px_-6px_rgb(15_118_110/0.6)] hover:bg-accent-800`
export const btnSecondary = `${btnBase} border border-slate-200 bg-white text-slate-800 shadow-sm hover:bg-slate-50`
export const btnGhost = `${btnBase} text-accent-800 hover:bg-accent-50`
export const card = 'rounded-3xl border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_8px_24px_-12px_rgb(15_23_42/0.1)] sm:p-6'
export const input =
  'min-h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-base text-slate-900 placeholder:text-slate-400 focus:border-accent-600 focus:outline-none focus:ring-4 focus:ring-accent-600/15'
export const pill = 'inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium'

export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
export const fmtDay = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

/** Calm, plain wording for a countdown. */
export function expiresIn(iso: string, now = Date.now()): string | null {
  const ms = new Date(iso).getTime() - now
  if (ms <= 0) return null
  const h = ms / 3600000
  if (h < 1) return `expires in ${Math.max(1, Math.round(ms / 60000))} minutes`
  if (h < 48) return `expires in ${Math.round(h)} hour${Math.round(h) === 1 ? '' : 's'}`
  return `expires in ${Math.round(h / 24)} days`
}

/** Never show raw API errors (e.g. "500: ...") to citizens. */
export function friendlyError(e: unknown, fallback: string): string {
  const m = e instanceof Error ? e.message : ''
  return m && !/^\d{3}\b/.test(m) && m.length < 120 ? m : fallback
}

/** "HOTEL CHECK-IN ONLY" -> "Hotel check-in" */
export function prettyPurpose(p: string | null): string {
  if (!p) return ''
  const t = p.replace(/\s+ONLY$/i, '').toLowerCase()
  return t.charAt(0).toUpperCase() + t.slice(1)
}
