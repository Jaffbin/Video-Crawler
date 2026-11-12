import { useId, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n'

/** State shared by a "?" button and the note it reveals, so the two can sit in different places. */
export function useHelpTip() {
  const [open, setOpen] = useState(false)
  const id = useId()
  return { open, id, toggle: () => setOpen((value) => !value) }
}

type Tip = ReturnType<typeof useHelpTip>

/** Small "?" that explains a setting on demand, keeping the form itself free of grey helper text. */
export function HelpButton({ tip, about }: { tip: Tip; about?: string }) {
  const { t } = useI18n()
  const label = about ? `${t('What is this?')} ${about}` : t('What is this?')
  return (
    <button
      type="button"
      className="help-tip"
      aria-expanded={tip.open}
      aria-controls={tip.open ? tip.id : undefined}
      aria-label={label}
      title={label}
      onClick={tip.toggle}
    >
      ?
    </button>
  )
}

export function HelpNote({ tip, children }: { tip: Tip; children: ReactNode }) {
  return tip.open ? (
    <div id={tip.id} role="note" className="help-note">
      {children}
    </div>
  ) : null
}
