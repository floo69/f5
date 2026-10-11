import { useCallback, useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS, ICONS2, PRESET_INFO } from '../helpers'
import { Icon } from '../ui'
import { btnBase, btnPrimary, btnSecondary, card, expiresIn, fmtDay, friendlyError, prettyPurpose } from './styles'

function Badge({ c, now }: { c: armor.Copy; now: number }) {
  const left = c.status === 'active' ? expiresIn(c.expires_at, now) : null
  if (c.status === 'revoked') return <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700 ring-1 ring-red-100">Revoked</span>
  if (c.status === 'expired' || !left) return <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200">Expired</span>
  return <span className="rounded-full bg-accent-50 px-2.5 py-1 text-xs font-semibold text-accent-800 ring-1 ring-accent-100">{left[0].toUpperCase() + left.slice(1)}</span>
}

function Confirm({ copy, busy, onCancel, onOk }: { copy: armor.Copy; busy: boolean; onCancel: () => void; onOk: () => void }) {
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    ref.current?.focus()
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onCancel])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center" role="alertdialog" aria-modal="true" aria-labelledby="revoke-title">
      <button type="button" aria-label="Cancel" tabIndex={-1} className="fade-in absolute inset-0 bg-slate-900/50" onClick={onCancel} />
      <div className="pop relative w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl">
        <h2 id="revoke-title" className="text-lg font-extrabold text-slate-900">Revoke this copy?</h2>
        <p className="mt-2 text-sm text-slate-600">
          {copy.recipient} will no longer be able to use it. Anyone who checks it will see that you withdrew it.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button ref={ref} type="button" onClick={onCancel} className={btnSecondary}>Keep it</button>
          <button type="button" disabled={busy} onClick={onOk} className={`${btnBase} bg-red-600 text-white hover:bg-red-700`}>{busy ? 'Revoking…' : 'Revoke'}</button>
        </div>
      </div>
    </div>
  )
}

export default function CopiesTab({ active, onProtect }: { active: boolean; onProtect: () => void }) {
  const [copies, setCopies] = useState<armor.Copy[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<armor.Copy | null>(null)
  const [busy, setBusy] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setCopies(await armor.listCopies())
      setError(null)
      setNow(Date.now())
    } catch (e) {
      setError(friendlyError(e, 'We couldn’t load your copies. Please try again.'))
    }
  }, [])

  useEffect(() => {
    if (active) void load()
  }, [active, load])

  const revoke = async () => {
    if (!confirm) return
    setBusy(true)
    try {
      const updated = await armor.revokeCopy(confirm.armor_id)
      setCopies((xs) => xs?.map((x) => (x.armor_id === updated.armor_id ? updated : x)) ?? xs)
      setConfirm(null)
    } catch (e) {
      setConfirm(null)
      setError(friendlyError(e, 'We couldn’t revoke that copy. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="fade-up">
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">My copies</h1>
        <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-600">
          <Icon d={ICONS.shield} className="h-4 w-4 shrink-0 text-accent-700" />Revoked copies fail verification instantly.
        </p>
      </div>
      {error && <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}

      {copies && copies.length === 0 && (
        <section className={`${card} fade-up py-10 text-center`}>
          <svg viewBox="0 0 120 90" className="mx-auto h-24 w-32" fill="none" aria-hidden="true">
            <rect x="14" y="22" width="92" height="56" rx="10" fill="#ccfbf1" />
            <rect x="24" y="12" width="72" height="50" rx="9" fill="#fff" stroke="#0f766e" strokeWidth="2.500" />
            <circle cx="42" cy="32" r="6" fill="#99f6e4" />
            <rect x="54" y="28" width="30" height="4" rx="2" fill="#cbd5e1" />
            <rect x="54" y="38" width="22" height="4" rx="2" fill="#f59e0b" />
          </svg>
          <h2 className="mt-4 text-lg font-bold text-slate-900">No copies yet</h2>
          <p className="mx-auto mt-1 max-w-xs text-sm text-slate-600">Every safe copy you make shows up here, so you can take it back any time.</p>
          <button type="button" onClick={onProtect} className={`${btnPrimary} mt-5`}>Protect your first ID</button>
        </section>
      )}

      <ul className="space-y-3">
        {copies?.map((c, i) => {
          const live = c.status === 'active' && expiresIn(c.expires_at, now) !== null
          return (
            <li key={c.armor_id} className={`${card} fade-up !p-4`} style={{ animationDelay: `${Math.min(i, 6) * 50}ms` }}>
              <div className="flex items-start gap-3">
                <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${live ? 'bg-accent-50 text-accent-700' : 'bg-slate-100 text-slate-400'}`}>
                  <Icon d={PRESET_INFO[c.preset]?.icon ?? ICONS2.note} className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-bold text-slate-900">{c.recipient}</p>
                  <p className="text-sm text-slate-600">{c.preset_label || prettyPurpose(c.purpose)}</p>
                </div>
                <Badge c={c} now={now} />
              </div>
              <div className="mt-3 flex items-center justify-between gap-3">
                <p className="text-xs text-slate-500">Issued {fmtDay(c.issued_at)}{c.status === 'revoked' && c.revoked_at ? ` · revoked ${fmtDay(c.revoked_at)}` : ''}</p>
                {live && (
                  <button type="button" onClick={() => setConfirm(c)} className="min-h-11 rounded-xl px-4 text-sm font-semibold text-red-700 ring-1 ring-red-100 transition hover:bg-red-50">
                    Revoke
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      {confirm && <Confirm copy={confirm} busy={busy} onCancel={() => setConfirm(null)} onOk={() => void revoke()} />}
    </div>
  )
}
