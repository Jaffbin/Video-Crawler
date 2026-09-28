import { Download, FolderOpen, Library, ListVideo, RefreshCw, Stethoscope, TimerReset } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AppView } from '../../hooks/useNavigation'
import { cn } from '../../lib/utils'

interface Props {
  view: AppView
  version: string
  online: boolean
  activeJobs: number
  failedJobs: number
  fileCount: number
  updateAttention: boolean
  environmentAttention: boolean
  onNavigate: (view: AppView) => void
  onDoctor: () => void
  onUpdate: () => void
  onOpenFolder: () => void
}

interface NavItem {
  id: AppView
  label: string
  shortLabel: string
  icon: LucideIcon
  count?: number
  bad?: boolean
}

function NavButton({ item, selected, onSelect }: { item: NavItem; selected: boolean; onSelect: () => void }) {
  const Icon = item.icon
  return (
    <button
      type="button"
      aria-current={selected ? 'page' : undefined}
      aria-label={item.label}
      onClick={onSelect}
      className={cn(
        'group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition',
        selected ? 'bg-white text-zinc-950' : 'text-zinc-400 hover:bg-white/[.06] hover:text-zinc-100',
      )}
    >
      <Icon size={18} aria-hidden />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      {!!item.count && (
        <span
          className={cn(
            'min-w-6 rounded-full px-1.5 py-0.5 text-center text-[11px] font-semibold',
            selected
              ? 'bg-black/10 text-zinc-800'
              : item.bad
                ? 'bg-red-500/15 text-red-300'
                : 'bg-white/[.08]',
          )}
        >
          {item.count > 99 ? '99+' : item.count}
        </span>
      )}
    </button>
  )
}

function ToolButton({
  icon: Icon,
  label,
  attention,
  onClick,
}: {
  icon: LucideIcon
  label: string
  attention?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-zinc-400 transition hover:bg-white/[.06] hover:text-zinc-100"
    >
      <Icon size={17} aria-hidden />
      <span>{label}</span>
      {attention && <i aria-label="Needs attention" className="ml-auto size-2 rounded-full bg-amber-400" />}
    </button>
  )
}

export function Sidebar(p: Props) {
  const items: NavItem[] = [
    { id: 'new', label: 'New download', shortLabel: 'New', icon: Download },
    {
      id: 'queue',
      label: 'Queue',
      shortLabel: 'Queue',
      icon: ListVideo,
      count: p.failedJobs || p.activeJobs,
      bad: p.failedJobs > 0,
    },
    { id: 'auto-download', label: 'Auto-download', shortLabel: 'Auto', icon: TimerReset },
    { id: 'library', label: 'Library', shortLabel: 'Library', icon: Library, count: p.fileCount },
  ]

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-white/[.06] bg-[#0b0d10] px-3 py-4 md:flex">
        <div className="mb-6 flex items-center gap-3 px-2">
          <div
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-xl bg-white font-black text-black"
          >
            ↓
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">Video Grabber</div>
            <div className="flex items-center gap-1.5 text-[11px] text-zinc-500">
              <i
                aria-hidden
                className={cn('size-1.5 rounded-full', p.online ? 'bg-emerald-400' : 'bg-red-400')}
              />
              {p.online ? `yt-dlp ${p.version}` : 'Reconnecting…'}
            </div>
          </div>
        </div>

        <nav aria-label="Main navigation" className="grid gap-1">
          {items.map((item) => (
            <NavButton
              key={item.id}
              item={item}
              selected={p.view === item.id}
              onSelect={() => p.onNavigate(item.id)}
            />
          ))}
        </nav>

        <div className="mt-auto grid gap-1 border-t border-white/[.06] pt-3">
          <ToolButton
            icon={Stethoscope}
            label="Diagnostics"
            attention={p.environmentAttention}
            onClick={p.onDoctor}
          />
          <ToolButton icon={RefreshCw} label="Updates" attention={p.updateAttention} onClick={p.onUpdate} />
          <ToolButton icon={FolderOpen} label="Open folder" onClick={p.onOpenFolder} />
        </div>
      </aside>

      <nav
        aria-label="Main navigation"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-white/[.08] bg-[#0b0d10]/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl md:hidden"
      >
        {items.map((item) => {
          const Icon = item.icon
          const selected = p.view === item.id
          return (
            <button
              key={item.id}
              type="button"
              aria-current={selected ? 'page' : undefined}
              onClick={() => p.onNavigate(item.id)}
              className={cn(
                'relative grid place-items-center gap-1 rounded-xl py-1.5 text-[11px] transition',
                selected ? 'bg-white text-zinc-950' : 'text-zinc-400',
              )}
            >
              <Icon size={18} aria-hidden />
              <span>{item.shortLabel}</span>
              {!!item.count && (
                <span
                  className={cn(
                    'absolute right-[calc(50%-22px)] top-0 min-w-4 rounded-full px-1 text-[9px] font-bold',
                    selected
                      ? 'bg-zinc-300 text-zinc-950'
                      : item.bad
                        ? 'bg-red-500 text-white'
                        : 'bg-zinc-700 text-white',
                  )}
                >
                  {item.count > 99 ? '99+' : item.count}
                </span>
              )}
            </button>
          )
        })}
      </nav>
    </>
  )
}
