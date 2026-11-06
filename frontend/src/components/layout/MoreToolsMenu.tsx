import { CircleHelp, Power } from 'lucide-react'
import { useEffect } from 'react'
import { useI18n } from '../../i18n'
import { Popover } from '../ui/Popover'

export function MoreToolsMenu({
  anchor,
  onClose,
  onSetup,
  onCloseBehavior,
}: {
  anchor: HTMLElement
  onClose: () => void
  onSetup: () => void
  onCloseBehavior?: () => void
}) {
  const { t } = useI18n()
  useEffect(() => {
    const resize = () => {
      if (window.innerWidth >= 1024) onClose()
    }
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [onClose])
  return (
    <Popover id="more-tools-menu" label={t('More tools')} anchor={anchor} onClose={onClose} actions>
      <button type="button" className="action-btn" onClick={onSetup}>
        <CircleHelp aria-hidden size={16} />
        {t('Getting started')}
      </button>
      {onCloseBehavior && (
        <button type="button" className="action-btn" onClick={onCloseBehavior}>
          <Power aria-hidden size={16} />
          {t('Close behavior')}
        </button>
      )}
    </Popover>
  )
}
