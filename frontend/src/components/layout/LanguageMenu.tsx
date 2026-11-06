import { Check } from 'lucide-react'
import { LOCALES, useI18n } from '../../i18n'
import { Popover } from '../ui/Popover'

export function LanguageMenu({ anchor, onClose }: { anchor: HTMLElement; onClose: () => void }) {
  const { locale, setLocale, t } = useI18n()
  return (
    <Popover id="language-menu" label={t('Language')} anchor={anchor} onClose={onClose} actions>
      {LOCALES.map((item) => (
        <button
          key={item.value}
          type="button"
          className="action-btn"
          aria-pressed={locale === item.value}
          onClick={() => setLocale(item.value)}
        >
          <span className="flex-1">{item.label}</span>
          {locale === item.value && <Check aria-hidden size={15} />}
        </button>
      ))}
    </Popover>
  )
}
