import { X } from 'lucide-react'
import type { ToastItem } from '../../hooks/useToasts'

/** role="status" makes screen readers announce new toasts without stealing focus. */
export function Toasts({ items, onRemove }: { items: ToastItem[]; onRemove: (id: number) => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 right-5 z-[60] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2"
    >
      {items.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-xl backdrop-blur ${
            t.error
              ? 'border-red-400/20 bg-red-950/70 text-red-100'
              : 'border-white/10 bg-[#16191f]/90 text-zinc-100'
          }`}
        >
          <span className="flex-1">{t.message}</span>
          <button type="button" onClick={() => onRemove(t.id)} aria-label="Dismiss message">
            <X size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}
