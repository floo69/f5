import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../api'
import ProgressCard from './ProgressCard'
import ResultView from './ResultView'
import UploadCard from './UploadCard'
import { ICONS2 } from './helpers'
import { Icon } from './ui'

type Phase = 'idle' | 'running' | 'result'

/** The original ThumbShield deed-redaction flow (behaviour unchanged), restyled container. */
export default function DeedsTab({ mock }: { mock: boolean }) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [samples, setSamples] = useState<api.Sample[]>([])
  const [job, setJob] = useState<api.Job | null>(null)
  const [filename, setFilename] = useState('')
  const [result, setResult] = useState<api.Result | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    void (async () => {
      try {
        setSamples(await api.listSamples())
        if (api.isMock() && api.mockVariant !== null && api.mockVariant !== '0') {
          setResult(api.mockResult())
          setPhase('result')
        }
      } catch (e) {
        if (api.isMock()) return
        setError(e instanceof Error ? e.message : 'Could not load samples')
      }
    })()
    return () => window.clearTimeout(timer.current)
  }, [mock])

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const j = await api.getJob(id)
        setJob(j)
        if (j.status === 'done' && j.result) {
          setResult(j.result)
          setPhase('result')
          return
        }
        if (j.status === 'error') {
          setError(j.error ?? 'Processing failed')
          setPhase('idle')
          return
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Lost connection to the local service')
        setPhase('idle')
        return
      }
      timer.current = window.setTimeout(tick, 500)
    }
    void tick()
  }, [])

  const start = async (name: string, run: () => Promise<{ job_id: string }>) => {
    setError(null)
    setJob(null)
    setFilename(name)
    setPhase('running')
    try {
      poll((await run()).job_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start processing')
      setPhase('idle')
    }
  }

  const reset = () => {
    window.clearTimeout(timer.current)
    setResult(null)
    setJob(null)
    setError(null)
    setPhase('idle')
  }

  return (
    <>
      <div className="mb-5 flex items-center gap-3 rounded-3xl bg-white px-5 py-4 shadow-sm ring-1 ring-slate-200/70">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-saffron-100 text-saffron-700">
          <Icon d={ICONS2.building} className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h1 className="text-lg font-extrabold tracking-tight text-slate-900">For registry offices</h1>
          <p className="text-sm text-slate-600">Remove thumbprints and Aadhaar numbers from land deeds before they are published.</p>
        </div>
      </div>
      {phase === 'idle' && (
        <UploadCard
          samples={samples}
          busy={false}
          error={error}
          onFile={(f) => void start(f.name, () => api.processFile(f))}
          onSample={(n) => void start(n + '.pdf', () => api.processSample(n))}
          onDemo={mock ? () => { setResult(api.mockResult()); setPhase('result') } : undefined}
        />
      )}
      {phase === 'running' && <ProgressCard job={job} filename={filename} />}
      {phase === 'result' && result && <ResultView result={result} mock={mock} onReset={reset} />}
    </>
  )
}
