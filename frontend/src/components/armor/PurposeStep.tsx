import * as armor from '../../armorApi'
import { ICONS2, PRESET_INFO } from '../helpers'
import { Icon } from '../ui'
import VoiceCard from './VoiceCard'
import { btnGhost, btnPrimary, card, input } from './styles'

export interface Purpose {
  preset: armor.PresetKey
  recipient: string
  days: number
}

interface Props {
  presets: armor.Preset[]
  value: Purpose
  onChange: (p: Purpose) => void
  onBack: () => void
  onRun: () => void
}

export default function PurposeStep({ presets, value, onChange, onBack, onRun }: Props) {
  const preset = presets.find((p) => p.key === value.preset)
  const setPreset = (key: armor.PresetKey) => {
    const p = presets.find((x) => x.key === key)
    onChange({ ...value, preset: key, days: p ? p.default_days : value.days })
  }
  const max = preset?.max_days ?? 1
  const days = Math.min(Math.max(1, value.days), max)
  const ok = Boolean(preset) && value.recipient.trim().length >= 3

  const onIntent = (i: armor.VoiceIntent) => {
    const p = presets.find((x) => x.key === i.preset) ?? preset
    const cap = p?.max_days ?? max
    const requested = i.valid_days ?? (i.preset ? p?.default_days : null) ?? value.days
    onChange({
      preset: p ? p.key : value.preset,
      recipient: i.recipient?.trim() || value.recipient,
      days: Math.min(Math.max(1, requested), cap),
    })
  }

  return (
    <div className="fade-up space-y-5 lg:space-y-8" aria-label="Who is it for">
      <div className="lg:text-center">
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 lg:text-4xl">Who is this copy for?</h2>
        <p className="mt-1 text-sm text-slate-600">We hide everything they don&rsquo;t need. The copy only works for them.</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start lg:gap-8">
      <div className="space-y-5">
      <section className={card} aria-label="Reason">
        <fieldset>
          <legend className="text-sm font-bold text-slate-900">What is it for?</legend>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            {presets.map((p) => {
              const info = PRESET_INFO[p.key]
              const on = p.key === value.preset
              return (
                <label key={p.key}
                  className={`flex min-h-16 cursor-pointer items-start gap-3 rounded-2xl border p-3.5 transition duration-200 focus-within:ring-4 focus-within:ring-accent-600/20 ${
                    on ? 'border-accent-600 bg-accent-50 shadow-sm' : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}>
                  <input type="radio" name="preset" className="sr-only" checked={on} onChange={() => setPreset(p.key)} />
                  <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${on ? 'bg-accent-700 text-white' : 'bg-slate-100 text-slate-600'}`}>
                    <Icon d={info?.icon ?? ICONS2.note} className="h-5 w-5" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-900">{p.label}</span>
                    <span className="mt-0.5 block text-xs leading-snug text-slate-600">
                      {info?.line ?? `Hides ${p.masks.join(', ').toLowerCase()}`}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>
      </section>

      <section className={`${card} space-y-5`} aria-label="Recipient and time">
        <div>
          <label htmlFor="recipient" className="text-sm font-bold text-slate-900">Who is it for?</label>
          <input id="recipient" className={`${input} mt-2`} value={value.recipient} placeholder="e.g. Taj Hotel, Goa" autoComplete="off"
            onChange={(e) => onChange({ ...value, recipient: e.target.value })} />
          {value.recipient.trim().length > 0 && value.recipient.trim().length < 3 && (
            <p className="mt-1.5 text-xs text-saffron-700">Please type at least 3 letters.</p>
          )}
        </div>
        <div>
          <span id="days-label" className="text-sm font-bold text-slate-900">How long should it work?</span>
          <div className="mt-2 flex items-center gap-3" role="group" aria-labelledby="days-label">
            <button type="button" aria-label="Fewer days" disabled={days <= 1} onClick={() => onChange({ ...value, days: days - 1 })}
              className="h-12 w-12 rounded-2xl border border-slate-200 bg-white text-xl font-semibold shadow-sm transition active:scale-95 disabled:opacity-40">−</button>
            <output className="min-w-24 text-center text-xl font-bold tabular-nums text-slate-900" aria-live="polite">{days} day{days === 1 ? '' : 's'}</output>
            <button type="button" aria-label="More days" disabled={days >= max} onClick={() => onChange({ ...value, days: days + 1 })}
              className="h-12 w-12 rounded-2xl border border-slate-200 bg-white text-xl font-semibold shadow-sm transition active:scale-95 disabled:opacity-40">+</button>
            <span className="text-xs text-slate-500">up to {max}</span>
          </div>
        </div>
      </section>

      </div>
      <div className="space-y-5 lg:sticky lg:top-24">
      <VoiceCard onIntent={onIntent} />

      {preset && (
        <section className="rounded-3xl bg-slate-900 p-5 text-white shadow-lg" aria-label="Stamp preview">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-saffron-500">
            <Icon d={ICONS2.sparkle} className="h-3.5 w-3.5" />Stamped on your copy
          </p>
          <p className="mt-2 break-words text-sm font-medium leading-relaxed text-amber-100" data-testid="wm-preview">
            {armor.watermarkText(preset, value.recipient, days)}
          </p>
          <p className="mt-2 text-xs text-slate-400">Anyone who sees this copy knows exactly what it can be used for.</p>
        </section>
      )}
      </div>
      </div>

      <div className="flex items-center gap-3 lg:mx-auto lg:max-w-xl">
        <button type="button" onClick={onBack} className={btnGhost}>Back</button>
        <button type="button" disabled={!ok} onClick={onRun} className={`${btnPrimary} min-h-14 flex-1 text-base`}>Protect my ID</button>
      </div>
    </div>
  )
}
