import { useEffect, useState } from 'react'
import * as api from './api'
import DeedsTab from './components/DeedsTab'
import AgentsTab from './components/armor/AgentsTab'
import ArmorTab from './components/armor/ArmorTab'
import CopiesTab from './components/armor/CopiesTab'
import { ICONS, ICONS2 } from './components/helpers'
import { Icon } from './components/ui'

type Tab = 'armor' | 'copies' | 'agents' | 'deeds'
const TABS: { key: Tab; label: string; short: string; icon: string }[] = [
  { key: 'armor', label: 'Protect', short: 'Protect', icon: ICONS.shield },
  { key: 'deeds', label: 'Deeds', short: 'Registry', icon: ICONS2.building },
  { key: 'copies', label: 'My copies', short: 'Copies', icon: ICONS2.list },
  { key: 'agents', label: 'Leak alerts', short: 'Alerts', icon: ICONS2.bell },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('armor')
  const [mock, setMock] = useState(api.isMock())
  const [ready, setReady] = useState(api.isMock())

  // Boot: ?mock=... forces fixtures; otherwise probe the backend and fall back to mock.
  useEffect(() => {
    if (api.isMock()) return
    void api.checkHealth().then((ok) => {
      if (!ok) {
        api.setMock(true)
        setMock(true)
      }
      setReady(true)
    })
  }, [])

  const go = (t: Tab) => {
    setTab(t)
    window.scrollTo({ top: 0 })
  }

  return (
    <div className="min-h-screen pb-28 md:pb-12">
      <header className="sticky top-0 z-30 border-b border-slate-200/60 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8 lg:py-4">
          <button type="button" onClick={() => go('armor')} className="flex min-w-0 items-center gap-2.5 text-left" aria-label="SurakshitID home">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent-600 to-accent-800 text-white shadow-sm">
              <Icon d={ICONS.shield} className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-base font-extrabold leading-tight tracking-tight text-slate-900">SurakshitID</span>
              <span className="block truncate text-[11px] leading-tight text-slate-500" lang="hi">सुरक्षित ID</span>
            </span>
          </button>
          <nav aria-label="Sections" className="hidden items-center gap-1.5 rounded-full bg-slate-100/80 p-1.5 md:flex">
            {TABS.map((t) => (
              <button key={t.key} type="button" onClick={() => go(t.key)} aria-current={tab === t.key ? 'page' : undefined}
                className={`flex min-h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold transition-all duration-200 ${tab === t.key ? 'bg-white text-accent-800 shadow-sm' : 'text-slate-600 hover:bg-white/50 hover:text-slate-900'}`}>
                <Icon d={t.icon} className="h-4 w-4" />
                {t.label}
              </button>
            ))}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            {mock && <span className="rounded-full bg-saffron-50 px-2.5 py-1 text-xs font-semibold text-saffron-700 ring-1 ring-saffron-100">Demo</span>}
          </div>
        </div>
      </header>

      <main className={`mx-auto px-4 py-6 sm:px-6 sm:py-10 lg:px-8 lg:py-12 ${tab === 'armor' || tab === 'deeds' ? 'max-w-6xl' : 'max-w-4xl'}`}>
        {ready && (
          <>
            <div hidden={tab !== 'armor'}><ArmorTab active={tab === 'armor'} /></div>
            <div hidden={tab !== 'deeds'}><DeedsTab mock={mock} /></div>
            <div hidden={tab !== 'copies'}><CopiesTab active={tab === 'copies'} onProtect={() => go('armor')} /></div>
            <div hidden={tab !== 'agents'}><AgentsTab /></div>
          </>
        )}
      </main>

      <nav aria-label="Sections" className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/70 bg-white/90 backdrop-blur-xl md:hidden">
        <ul className="mx-auto grid max-w-md grid-cols-4">
          {TABS.map((t) => (
            <li key={t.key}>
              <button type="button" onClick={() => go(t.key)} aria-current={tab === t.key ? 'page' : undefined} aria-label={t.label}
                className={`flex min-h-16 w-full flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors ${tab === t.key ? 'text-accent-700' : 'text-slate-500'}`}>
                <span className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors duration-200 ${tab === t.key ? 'bg-accent-100' : ''}`}>
                  <Icon d={t.icon} className="h-5 w-5" />
                </span>
                {t.short}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}
