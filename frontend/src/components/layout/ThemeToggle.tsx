import { Moon, Sun } from 'lucide-react'
import { useI18n } from '../../i18n'
import type { Theme } from '../../hooks/useTheme'

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: (button: HTMLElement) => void }) {
  const { t } = useI18n()
  return (
    <button
      type="button"
      role="switch"
      aria-checked={theme === 'dark'}
      aria-label={t('Dark mode')}
      title={t(theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode')}
      className="theme-toggle"
      data-mode={theme}
      onClick={(event) => onToggle(event.currentTarget)}
    >
      <svg className="theme-toggle-frame" viewBox="0 0 104 44" fill="none" aria-hidden="true">
        <path d="M12 2 H92 L102 22 L92 42 H12 L2 22 Z" />
      </svg>
      <span className="theme-toggle-selection" aria-hidden="true" />
      <Sun className="theme-toggle-sun" size={25} strokeWidth={2} aria-hidden="true" />
      <Moon className="theme-toggle-moon" size={25} strokeWidth={2} aria-hidden="true" />
    </button>
  )
}
