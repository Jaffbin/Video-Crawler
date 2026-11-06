import { useState } from 'react'
import { useI18n } from '../../i18n'
import { Button } from './Button'
import { Modal } from './Modal'

export function SelectionScope({
  items,
  visible,
  disabled,
  onClear,
  onRemove,
}: {
  items: { key: string; label: string }[]
  visible: string[]
  disabled?: boolean
  onClear: () => void
  onRemove: (key: string) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const visibleSet = new Set(visible)
  const hidden = items.filter((item) => !visibleSet.has(item.key)).length
  return (
    <>
      {hidden > 0 && (
        <span role="status" className="text-amber-300">
          {t('{count} selected outside this view', { count: hidden })}
        </span>
      )}
      {!!items.length && (
        <>
          <Button disabled={disabled} onClick={() => setOpen(true)}>
            {t('View selected')}
          </Button>
          <Button disabled={disabled} onClick={onClear}>
            {t('Clear selection')}
          </Button>
        </>
      )}
      <Modal open={open} title={t('Selected items')} onClose={() => setOpen(false)}>
        <p className="mb-3 text-sm text-zinc-400">
          {t('Selections include other pages and filtered-out items.')}
        </p>
        <ul className="grid gap-3">
          {items.map((item) => (
            <li key={item.key}>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked disabled={disabled} onChange={() => onRemove(item.key)} />
                <span className="min-w-0 break-words">
                  {item.label}
                  {!visibleSet.has(item.key) && (
                    <span className="block text-xs text-amber-300">{t('Outside this view')}</span>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>
        {!items.length && <p>{t('No items selected.')}</p>}
      </Modal>
    </>
  )
}
