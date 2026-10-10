import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'
import Header from './components/Header'
import ProgressCard from './components/ProgressCard'
import ResultView from './components/ResultView'
import UploadCard from './components/UploadCard'
import OperationsPanel from './components/OperationsPanel'
import AuditPortal from './components/AuditPortal'

type Phase = 'idle' | 'running' | 'result'

export default function App() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [mock] = useState(api.isMock())
  const [runtime, setRuntime] = useState<api.RuntimeStatus | null>(null)
  const [samples, setSamples] = useState<api.Sample[]>([])
  const [job, setJob] = useState<api.Job | null>(null)
  const [filename, setFilename] = useState('')
  const [result, setResult] = useState<api.Result | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | undefined>(undefined)

  // Boot: mock mode is explicit via ?mock=...; normal mode requires the local API.
  useEffect(() => {
    void (async () => {
      if (api.isMock()) {
        setSamples(await api.listSamples())
        if (api.mockVariant !== null && api.mockVariant !== '0') {
          setResult(api.mockResult())
          setPhase('result')
        }
        return
      }
      try { setRuntime(await api.runtimeStatus()) } catch { /* health check below reports the actionable error */ }
      if (await api.checkHealth()) {
        try {
          setSamples(await api.listSamples())
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Could not load samples')
        }
      } else {
        setError('The local API is unavailable. Start backend.app.main on port 8000, then refresh.')
      }
    })()
    return () => window.clearTimeout(timer.current)
  }, [])

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
    <div className="min-h-screen">
      <Header mock={mock} status={runtime} />
      <main className="mx-auto max-w-7xl px-8 py-10">
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
        {phase === 'result' && result && (
          <ResultView result={result} mock={mock} onReset={reset} />
        )}
        <OperationsPanel />
        <AuditPortal />
      </main>
    </div>
  )
}
