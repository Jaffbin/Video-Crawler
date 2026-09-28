import { Bell, BellRing, FolderOpen, RefreshCw, Stethoscope } from 'lucide-react'
import { Button } from '../ui/Button'

export type NotificationMode = 'server' | 'default' | 'granted' | 'denied' | 'unsupported'

interface Props {
  title: string
  description: string
  version: string
  online: boolean
  updateAttention: boolean
  environmentAttention: boolean
  notification: NotificationMode
  onDoctor: () => void
  onUpdate: () => void
  onOpenFolder: () => void
  onNotify: () => void
}

const Dot = () => <i aria-hidden className="absolute right-1 top-1 size-2 rounded-full bg-amber-400" />

export function Header(p: Props) {
  const notifyLabel = { default: 'Notify', granted: 'Notifications on', denied: 'Notifications blocked' }[
    p.notification as 'default' | 'granted' | 'denied'
  ]
  return (
    <header className="sticky top-0 z-30 border-b border-white/[.06] bg-[#0b0d10]/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-base font-semibold">{p.title}</h1>
            </div>
            <div className="truncate text-xs text-zinc-400">{p.description}</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-zinc-500 md:hidden">
              <i
                aria-hidden
                className={`size-1.5 rounded-full ${p.online ? 'bg-emerald-400' : 'bg-red-400'}`}
              />
              {p.online ? `Local service connected · yt-dlp ${p.version}` : 'Reconnecting…'}
            </div>
          </div>
        </div>

        <nav aria-label="Tools" className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            onClick={p.onDoctor}
            aria-label="Diagnostics"
            className="relative md:hidden"
          >
            <Stethoscope size={16} />
            {p.environmentAttention && <Dot />}
          </Button>
          <Button variant="ghost" onClick={p.onUpdate} aria-label="Updates" className="relative md:hidden">
            <RefreshCw size={16} />
            {p.updateAttention && <Dot />}
          </Button>
          <Button
            variant="ghost"
            onClick={p.onOpenFolder}
            aria-label="Open download folder"
            className="md:hidden"
          >
            <FolderOpen size={16} />
          </Button>
          {p.notification !== 'server' && p.notification !== 'unsupported' && (
            <Button
              variant="ghost"
              onClick={p.onNotify}
              disabled={p.notification === 'denied'}
              aria-label={notifyLabel}
              title={notifyLabel}
            >
              {p.notification === 'granted' ? <BellRing size={16} /> : <Bell size={16} />}
              <span className="hidden lg:inline">{notifyLabel}</span>
            </Button>
          )}
        </nav>
      </div>
    </header>
  )
}
