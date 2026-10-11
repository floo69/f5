import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'
import Header from './components/Header'
import ProgressCard from './components/ProgressCard'
import ResultView from './components/ResultView'
import UploadCard from './components/UploadCard'
import SurakshitID from './components/SurakshitID'

type Phase = 'idle' | 'running' | 'result'
type AppMode = 'thumbshield' | 'surakshit'

export default function App() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [mock, setMock] = useState(api.isMock())
  const [samples, setSamples] = useState<api.Sample[]>([])
  const [job, setJob] = useState<api.Job | null>(null)
  const [filename, setFilename] = useState('')
  const [result, setResult] = useState<api.Result | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<AppMode>('thumbshield')
  const timer = useRef<number | undefined>(undefined)

  const enableMock = useCallback(async () => {
    api.setMock(true)
    setMock(true)
    setSamples(await api.listSamples())
  }, [])

  // Boot: auto-load fixture with ?mock=..., else probe the backend and fall back to mock.
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
      if (await api.checkHealth()) {
        try {
          setSamples(await api.listSamples())
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Could not load samples')
        }
      } else {
        await enableMock()
      }
    })()
    return () => window.clearTimeout(timer.current)
  }, [enableMock])

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
      <Header mock={mock} mode={mode} onModeChange={setMode} />
      <main className="mx-auto max-w-7xl px-8 py-10">
        {mode === 'surakshit' ? <SurakshitID /> : (
          <>
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
          </>
        )}
      </main>
    </div>
  )
}
