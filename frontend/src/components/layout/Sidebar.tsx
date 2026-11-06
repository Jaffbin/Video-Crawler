import {
  CircleHelp,
  Download,
  FolderOpen,
  Languages,
  Library,
  ListVideo,
  Power,
  Settings,
  TimerReset,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AppView } from '../../hooks/useNavigation'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n'

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
  onTools: () => void
  onSetup: () => void
  onOpenFolder: () => void
  onLanguage: (button: HTMLElement) => void
  onCloseBehavior?: () => void
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
              ? 'bg-zinc-950/10 text-zinc-800'
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
  popup,
}: {
  icon: LucideIcon
  label: string
  attention?: boolean
  onClick: (button: HTMLButtonElement) => void
  popup?: boolean
}) {
  const { t } = useI18n()
  return (
    <button
      type="button"
      onClick={(event) => onClick(event.currentTarget)}
      aria-haspopup={popup ? 'dialog' : undefined}
      className="relative flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm text-zinc-400 transition hover:bg-white/[.06] hover:text-zinc-100"
    >
      <Icon size={17} aria-hidden />
      <span>{label}</span>
      {attention && (
        <i aria-label={t('Needs attention')} className="ml-auto size-2 rounded-full bg-amber-400" />
      )}
    </button>
  )
}

export function Sidebar(p: Props) {
  const { t } = useI18n()
  const items: NavItem[] = [
    { id: 'new', label: t('New download'), shortLabel: t('New'), icon: Download },
    {
      id: 'queue',
      label: t('Queue'),
      shortLabel: t('Queue'),
      icon: ListVideo,
      count: p.failedJobs || p.activeJobs,
      bad: p.failedJobs > 0,
    },
    { id: 'auto-download', label: t('Auto-download'), shortLabel: t('Auto'), icon: TimerReset },
    { id: 'library', label: t('Library'), shortLabel: t('Library'), icon: Library, count: p.fileCount },
  ]

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col overflow-y-auto border-r border-white/[.06] bg-canvas px-3 py-4 lg:flex">
        <div className="mb-6 flex items-center gap-3 px-2">
          <div
            aria-hidden
            className="grid size-9 shrink-0 place-items-center rounded-xl bg-white font-black text-zinc-950"
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
              {p.online ? `yt-dlp ${p.version}` : t('Reconnecting')}
            </div>
          </div>
        </div>

        <nav aria-label={t('Main navigation')} className="grid gap-1">
          {items.map((item) => (
            <NavButton
              key={item.id}
              item={item}
              selected={p.view === item.id}
              onSelect={() => p.onNavigate(item.id)}
            />
          ))}
        </nav>

        <div className="compact-actions sidebar-tools mt-auto grid gap-1 border-t border-white/[.06] pt-3">
          <ToolButton icon={CircleHelp} label={t('Getting started')} onClick={p.onSetup} />
          <ToolButton icon={FolderOpen} label={t('Open folder')} onClick={p.onOpenFolder} />
          <ToolButton icon={Languages} label={t('Language')} onClick={p.onLanguage} popup />
          <ToolButton
            icon={Settings}
            label={t('Settings and help')}
            attention={p.environmentAttention || p.updateAttention}
            onClick={p.onTools}
          />
          {p.onCloseBehavior && (
            <ToolButton icon={Power} label={t('Close behavior')} onClick={p.onCloseBehavior} />
          )}
        </div>
      </aside>

      <nav
        aria-label={t('Main navigation')}
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-white/[.08] bg-canvas/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl lg:hidden"
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
                        ? 'bg-red-500 text-[#fff]'
                        : 'bg-zinc-700 text-zinc-100',
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
