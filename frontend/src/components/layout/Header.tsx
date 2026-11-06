import { Bell, BellRing, Ellipsis, Languages, Settings } from 'lucide-react'
import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'
import { ThemeToggle } from './ThemeToggle'
import type { Theme } from '../../hooks/useTheme'

export type NotificationMode =
  'server' | 'default' | 'granted' | 'denied' | 'unsupported' | 'native-on' | 'native-off'

interface Props {
  title: string
  description: string
  version: string
  online: boolean
  updateAttention: boolean
  environmentAttention: boolean
  notification: NotificationMode
  onTools: () => void
  onNotify: () => void
  theme: Theme
  onToggleTheme: (button: HTMLElement) => void
  onLanguage: (button: HTMLElement) => void
  onMoreTools: (button: HTMLElement) => void
  moreToolsOpen: boolean
}

const Dot = () => <i aria-hidden className="absolute right-1 top-1 size-2 rounded-full bg-amber-400" />

export function Header(p: Props) {
  const { t } = useI18n()
  const notifyLabel = {
    default: t('Notify'),
    granted: t('Notifications on'),
    denied: t('Notifications blocked'),
    'native-on': t('Turn off completion notifications'),
    'native-off': t('Turn on completion notifications'),
  }[p.notification as 'default' | 'granted' | 'denied' | 'native-on' | 'native-off']
  return (
    <header className="shrink-0 z-30 border-b border-white/[.06] bg-canvas/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="header-heading flex min-w-0 items-center gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-base font-semibold">{p.title}</h1>
            </div>
            <div className="header-description truncate text-xs text-zinc-400">{p.description}</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-zinc-500 lg:hidden">
              <i
                aria-hidden
                className={`size-1.5 rounded-full ${p.online ? 'bg-emerald-400' : 'bg-red-400'}`}
              />
              {p.online ? `${t('Local service connected')} · yt-dlp ${p.version}` : t('Reconnecting')}
            </div>
          </div>
        </div>

        <nav aria-label={t('Tools')} className="ml-auto flex shrink-0 items-center gap-1.5">
          <ThemeToggle theme={p.theme} onToggle={p.onToggleTheme} />
          <Button
            variant="ghost"
            className="lg:hidden"
            aria-label={t('Language')}
            title={t('Language')}
            aria-haspopup="dialog"
            onClick={(event) => p.onLanguage(event.currentTarget)}
          >
            <Languages aria-hidden size={16} />
          </Button>
          <Button
            variant="ghost"
            onClick={p.onTools}
            aria-label={t('Settings and help')}
            className="relative lg:hidden"
          >
            <Settings aria-hidden size={18} />
            {(p.environmentAttention || p.updateAttention) && <Dot />}
          </Button>
          <Button
            variant="ghost"
            className="lg:hidden"
            aria-label={t('More tools')}
            title={t('More tools')}
            aria-haspopup="dialog"
            aria-expanded={p.moreToolsOpen}
            aria-controls={p.moreToolsOpen ? 'more-tools-menu' : undefined}
            onClick={(event) => p.onMoreTools(event.currentTarget)}
          >
            <Ellipsis aria-hidden size={18} />
          </Button>
          {p.notification !== 'server' && p.notification !== 'unsupported' && (
            <Button
              variant="ghost"
              onClick={p.onNotify}
              disabled={p.notification === 'denied'}
              aria-label={notifyLabel}
              title={notifyLabel}
              aria-pressed={p.notification.startsWith('native-') ? p.notification === 'native-on' : undefined}
            >
              {p.notification === 'granted' || p.notification === 'native-on' ? (
                <BellRing size={16} />
              ) : (
                <Bell size={16} />
              )}
              <span className="hidden lg:inline">
                {p.notification === 'native-on'
                  ? t('Notifications on')
                  : p.notification === 'native-off'
                    ? t('Notifications off')
                    : notifyLabel}
              </span>
            </Button>
          )}
        </nav>
      </div>
    </header>
  )
}
