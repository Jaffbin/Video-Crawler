import { Bell, BellRing, FolderOpen, RefreshCw, Stethoscope } from 'lucide-react'
import { Button } from '../ui/Button'

export type NotificationMode = 'server' | 'default' | 'granted' | 'denied' | 'unsupported'

interface Props {
  version: string
  online: boolean
  windowMode: boolean
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
          <div
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-xl bg-white font-black text-black"
          >
            ↓
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-sm font-semibold">Video Grabber</h1>
              <span className="hidden rounded-md bg-white/[.06] px-1.5 py-0.5 font-mono text-xs text-zinc-400 sm:inline">
                yt-dlp {p.version}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <i
                aria-hidden
                className={`size-1.5 rounded-full ${p.online ? 'bg-emerald-400' : 'bg-red-400'}`}
              />
              {p.online ? 'Local service connected' : 'Reconnecting…'}
            </div>
          </div>
        </div>

        <nav aria-label="Tools" className="flex items-center gap-1.5">
          <Button variant="ghost" onClick={p.onDoctor} aria-label="Diagnostics" className="relative">
            <Stethoscope size={16} />
            <span className="hidden lg:inline">Diagnostics</span>
            {p.environmentAttention && <Dot />}
          </Button>
          <Button variant="ghost" onClick={p.onUpdate} aria-label="Updates" className="relative">
            <RefreshCw size={16} />
            <span className="hidden lg:inline">Update</span>
            {p.updateAttention && <Dot />}
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
          <Button variant="ghost" onClick={p.onOpenFolder} aria-label="Open download folder">
            <FolderOpen size={16} />
            <span className="hidden xl:inline">Downloads</span>
          </Button>
        </nav>
      </div>
    </header>
  )
}
