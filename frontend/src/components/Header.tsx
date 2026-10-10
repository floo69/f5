import { ICONS } from './helpers'
import { Icon } from './ui'

export default function Header({ mock }: { mock: boolean }) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-8 py-5">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-700 text-white shadow-sm">
            <Icon d={ICONS.shield} className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">ThumbShield</h1>
            <p className="text-sm text-slate-500">Protect citizens&apos; biometrics before you publish</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {mock && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
              Demo mode · sample data
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-50 px-3 py-1.5 text-xs font-medium text-accent-800 ring-1 ring-accent-100">
            <Icon d={ICONS.lock} className="h-3.5 w-3.5" />
            Runs locally · no document leaves this machine
          </span>
        </div>
      </div>
    </header>
  )
}
