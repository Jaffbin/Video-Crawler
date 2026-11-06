import { X } from 'lucide-react'
import { useState } from 'react'
import type { ToastItem } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'

/** role="status" makes screen readers announce new toasts without stealing focus. */
export function Toasts({ items, onRemove }: { items: ToastItem[]; onRemove: (id: number) => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 right-5 z-[60] flex max-h-[50vh] w-[min(380px,calc(100vw-2rem))] flex-col gap-2 overflow-y-auto"
      style={{ bottom: 'calc(var(--audio-toast-offset, 0px) + 1.25rem)' }}
    >
      {items.map((item) => (
        <ToastMessage key={item.id} item={item} onRemove={() => onRemove(item.id)} />
      ))}
    </div>
  )
}

function ToastMessage({ item, onRemove }: { item: ToastItem; onRemove: () => void }) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function act() {
    setBusy(true)
    setError('')
    try {
      await item.action?.onClick()
      onRemove()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'Could not undo. Try again or open Recovery.'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div
      className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-xl backdrop-blur ${item.error ? 'border-red-400/20 bg-error-surface/95 text-red-100' : 'border-white/10 bg-toast/95 text-zinc-100'}`}
    >
      <div className="flex-1">
        <p>{item.message}</p>
        {error && (
          <p role="alert" className="mt-1 text-red-300">
            {error}
          </p>
        )}
        {item.action && (
          <button type="button" className="action-btn mt-2" disabled={busy} onClick={act}>
            {t(busy ? 'Restoring…' : item.action.label)}
          </button>
        )}
      </div>
      <button type="button" disabled={busy} onClick={onRemove} aria-label={t('Dismiss message')}>
        <X size={15} />
      </button>
    </div>
  )
}
