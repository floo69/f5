import { useEffect, useRef, useState } from 'react'
import * as armor from '../../armorApi'
import { ICONS } from '../helpers'
import { Icon } from '../ui'
import { btnSecondary, input } from './styles'

const MISSING: Record<string, string> = { recipient: 'who it is for', preset: 'what it is for' }

interface Rec {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  processLocally?: boolean
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type RecCtor = new () => Rec
const getCtor = (): RecCtor | undefined => {
  const w = window as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export default function VoiceCard({ onIntent }: { onIntent: (i: armor.VoiceIntent) => void }) {
  const [supported] = useState(() => getCtor() !== undefined)
  const [listening, setListening] = useState(false)
  const [text, setText] = useState('')
  const [intent, setIntent] = useState<armor.VoiceIntent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<Rec | null>(null)

  useEffect(() => () => { rec.current?.stop(); window.speechSynthesis?.cancel() }, [])

  const send = async (t: string) => {
    if (!t.trim()) return
    setError(null)
    try {
      const i = await armor.parseVoice(t)
      setIntent(i)
      onIntent(i)
      if ('speechSynthesis' in window && i.confirmation) {
        window.speechSynthesis.cancel()
        const u = new SpeechSynthesisUtterance(i.confirmation)
        u.lang = 'en-IN'
        window.speechSynthesis.speak(u)
      }
    } catch (e) {
      void e
      setError('We couldn\u2019t understand that. Try typing it like: Share my Aadhaar with Taj Hotel for 2 days.')
    }
  }

  // First try on-device en-IN; if the browser can't do that, retry once with its default
  // recogniser (en-US); if speech still isn't available, quietly point to the text box.
  const listen = (fallback = false) => {
    const C = getCtor()
    if (!C) return
    if (listening && !fallback) { rec.current?.stop(); return }
    setError(null)
    const r = new C()
    r.lang = fallback ? 'en-US' : 'en-IN'
    r.interimResults = false
    r.maxAlternatives = 1
    if (!fallback && 'processLocally' in r) r.processLocally = true
    r.onresult = (e) => {
      const t = e.results[0]?.[0]?.transcript ?? ''
      setText(t)
      void send(t)
    }
    r.onerror = (e) => {
      setListening(false)
      if (e.error === 'no-speech' || e.error === 'aborted') return
      if (!fallback && ['language-not-supported', 'service-not-allowed', 'network'].includes(e.error)) {
        listen(true)
        return
      }
      setError('Voice isn\u2019t available in this browser. Please type it instead.')
    }
    r.onend = () => setListening(false)
    rec.current = r
    setListening(true)
    try { r.start() } catch { setListening(false) }
  }

  return (
    <div className="rounded-3xl bg-gradient-to-br from-saffron-50 to-white p-4 ring-1 ring-saffron-100 sm:p-5">
      <h3 className="flex items-center gap-2 text-sm font-bold text-slate-900">
        <Icon d={ICONS.mic} className="h-4 w-4 text-saffron-600" />Or just say it
      </h3>
      <p className="mt-1 text-sm text-slate-600">&ldquo;Share my Aadhaar with Taj Hotel for 2 days&rdquo;</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        {supported && (
          <button type="button" onClick={() => listen()} aria-pressed={listening}
            aria-label={listening ? 'Stop listening' : 'Start voice command'}
            className={`flex min-h-12 shrink-0 items-center justify-center gap-2 rounded-2xl px-4 text-sm font-semibold text-white transition ${listening ? 'bg-red-600' : 'bg-saffron-600 hover:bg-saffron-700'}`}>
            <Icon d={ICONS.mic} className="h-5 w-5" />{listening ? 'Listening…' : 'Speak'}
          </button>
        )}
        <form className="flex min-w-0 flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); void send(text) }}>
          <input className={input} value={text} onChange={(e) => setText(e.target.value)} aria-label="Type what you want to do"
            placeholder="Or type it here" />
          <button type="submit" className={btnSecondary} disabled={!text.trim()}>Go</button>
        </form>
      </div>
      {error && <p role="status" className="mt-2 text-sm text-amber-800">{error}</p>}
      {intent && (
        <div className="mt-3 rounded-2xl bg-white px-4 py-3 text-sm shadow-sm ring-1 ring-slate-100" role="status">
          <p className="text-slate-800">{intent.confirmation}</p>
          {intent.missing.length > 0 && (
            <p className="mt-1 font-medium text-amber-800">Still need: {intent.missing.map((m) => MISSING[m] ?? m).join(' and ')}</p>
          )}
        </div>
      )}
    </div>
  )
}
