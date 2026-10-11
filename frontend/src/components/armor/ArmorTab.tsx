import { useCallback, useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import CaptureStep, { type Captured } from './CaptureStep'
import PurposeStep, { type Purpose } from './PurposeStep'
import ResultPanel from './ResultPanel'
import Timeline from './Timeline'
import { friendlyError } from './styles'

type Phase = 'capture' | 'purpose' | 'running' | 'result'
const STEPS = ['Add photo', 'Choose who it\u2019s for', 'Done']
const STEP_OF: Record<Phase, number> = { capture: 0, purpose: 1, running: 2, result: 2 }

export default function ArmorTab({ active }: { active: boolean }) {
  const [phase, setPhase] = useState<Phase>('capture')
  const [captured, setCaptured] = useState<Captured | null>(null)
  const [presets, setPresets] = useState<armor.Preset[]>([])
  const [purpose, setPurpose] = useState<Purpose>({ preset: 'hotel', recipient: '', days: 2 })
  const [job, setJob] = useState<armor.ArmorJob | null>(null)
  const [result, setResult] = useState<armor.ArmorResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const gen = useRef(0)

  useEffect(() => {
    armor.listPresets().then(setPresets, (e: unknown) => setError(friendlyError(e, 'We could not load the options. Please try again.')))
    return () => window.clearTimeout(timer.current)
  }, [])

  const poll = useCallback((id: string, g: number) => {
    const tick = async () => {
      if (g !== gen.current) return
      try {
        const j = await armor.getArmorJob(id)
        if (g !== gen.current) return
        setJob(j)
        if (j.status === 'done' && j.result) {
          setResult(j.result)
          setPhase('result')
          return
        }
        if (j.status === 'error') {
          setError('Something went wrong while protecting your ID. Please try again.')
          setPhase('purpose')
          return
        }
      } catch (e) {
        setError(friendlyError(e, 'We lost connection. Please try again.'))
        setPhase('purpose')
        return
      }
      timer.current = window.setTimeout(tick, 400)
    }
    void tick()
  }, [])

  const run = async () => {
    if (!captured) return
    const preset = presets.find((p) => p.key === purpose.preset)
    const days = Math.min(Math.max(1, purpose.days), preset?.max_days ?? purpose.days)
    const g = ++gen.current
    setError(null)
    setJob(null)
    setResult(null)
    setPhase('running')
    try {
      const { job_id } = await armor.startArmor({
        file: captured.file, filename: captured.file.name, preset: purpose.preset,
        recipient: purpose.recipient.trim(), valid_days: days, source: captured.source,
      })
      poll(job_id, g)
    } catch (e) {
      setError(friendlyError(e, 'We could not start. Please try again.'))
      setPhase('purpose')
    }
  }

  const reset = () => {
    gen.current++
    window.clearTimeout(timer.current)
    setCaptured(null)
    setResult(null)
    setJob(null)
    setPhase('capture')
  }
  const idx = STEP_OF[phase]

  return (
    <div className="space-y-5">
      <ol className="flex items-center justify-center gap-2 text-xs font-semibold sm:text-sm" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li key={label} aria-current={i === idx ? 'step' : undefined} className="flex items-center gap-2">
            <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs transition-colors duration-300 ${i <= idx ? 'bg-accent-700 text-white' : 'bg-slate-200 text-slate-500'}`}>{i + 1}</span>
            <span className={i === idx ? 'text-slate-900' : 'hidden text-slate-500 sm:inline'}>{label}</span>
            {i < STEPS.length - 1 && <span aria-hidden="true" className={`h-px w-4 sm:w-8 ${i < idx ? 'bg-accent-600' : 'bg-slate-300'}`} />}
          </li>
        ))}
      </ol>
      {error && <p role="alert" className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-800 ring-1 ring-red-100">{error}</p>}

      {phase === 'capture' && (
        <CaptureStep active={active} captured={captured} onCaptured={setCaptured} onNext={() => setPhase('purpose')} />
      )}
      {phase === 'purpose' && (
        <PurposeStep presets={presets} value={purpose} onChange={setPurpose} onBack={() => setPhase('capture')} onRun={() => void run()} />
      )}
      {phase === 'running' && (
        <Timeline steps={job?.steps ?? pendingSteps()} />
      )}
      {phase === 'result' && result && (
        <ResultPanel result={result} jobId={job?.job_id ?? result.armor_id} onPurpose={() => setPhase('purpose')} onRetake={reset} onReset={reset} />
      )}
    </div>
  )
}

const pendingSteps = (): armor.Step[] =>
  ['capture', 'preprocess', 'detect', 'decide', 'destroy', 'watermark', 'verify', 'seal'].map((k) => ({
    key: k, label: k[0].toUpperCase() + k.slice(1), status: 'pending', ms: null,
  }))
