import { X } from 'lucide-react'
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useI18n } from '../../i18n'

const FOCUSABLE =
  'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'

export function placePopover(
  anchor: DOMRect,
  width: number,
  height: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const margin = 12
  const gap = 8
  const below = viewportHeight - anchor.bottom - gap - margin
  const above = anchor.top - gap - margin
  const maxHeight = Math.max(0, viewportHeight - margin * 2)
  const visibleHeight = Math.min(height, maxHeight)
  const upward = visibleHeight > below && above > below
  const preferredTop = upward ? anchor.top - gap - visibleHeight : anchor.bottom + gap
  return {
    left: Math.max(margin, Math.min(anchor.left, viewportWidth - width - margin)),
    top: Math.max(margin, Math.min(preferredTop, viewportHeight - margin - visibleHeight)),
    maxHeight,
  }
}

interface Props {
  id: string
  label: string
  anchor: HTMLElement
  onClose: () => void
  actions?: boolean
  children: ReactNode
}

/** A non-modal floating panel, outside the scrolling/card layout. */
export function Popover({ id, label, anchor, onClose, actions = false, children }: Props) {
  const { t } = useI18n()
  const panel = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  const [position, setPosition] = useState<ReturnType<typeof placePopover> | null>(null)

  function dismiss(restoreFocus: boolean) {
    if (restoreFocus && anchor.isConnected) anchor.focus({ preventScroll: true })
    close.current()
  }

  useLayoutEffect(() => {
    const element = panel.current!
    let anchorPosition = anchor.getBoundingClientRect()
    const update = () => {
      if (!anchor.isConnected) {
        close.current()
        return
      }
      const rect = anchor.getBoundingClientRect()
      anchorPosition = rect
      const bounds = element.getBoundingClientRect()
      const height = element.scrollHeight + element.offsetHeight - element.clientHeight
      const next = placePopover(rect, bounds.width, height, innerWidth, innerHeight)
      setPosition((previous) =>
        previous?.left === next.left && previous.top === next.top && previous.maxHeight === next.maxHeight
          ? previous
          : next,
      )
    }
    update()
    const first = content.current?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first || element).focus({ preventScroll: true })

    const outside = (event: Event) => {
      const target = event.target as Node
      if (!element.contains(target) && !anchor.contains(target)) close.current()
    }
    const scroll = (event: Event) => {
      if (event.target instanceof Node && element.contains(event.target)) return
      const rect = anchor.getBoundingClientRect()
      // A queued scroll event from before opening must not immediately dismiss the panel.
      if (Math.abs(rect.top - anchorPosition.top) > 0.5 || Math.abs(rect.left - anchorPosition.left) > 0.5)
        close.current()
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      if (anchor.isConnected) anchor.focus({ preventScroll: true })
      close.current()
    }
    document.addEventListener('pointerdown', outside, true)
    document.addEventListener('focusin', outside)
    document.addEventListener('keydown', escape)
    window.addEventListener('scroll', scroll, true)
    window.addEventListener('resize', update)
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null
    observer?.observe(element)
    observer?.observe(anchor)
    return () => {
      document.removeEventListener('pointerdown', outside, true)
      document.removeEventListener('focusin', outside)
      document.removeEventListener('keydown', escape)
      window.removeEventListener('scroll', scroll, true)
      window.removeEventListener('resize', update)
      observer?.disconnect()
    }
  }, [anchor])

  return createPortal(
    <div
      ref={panel}
      id={id}
      role="dialog"
      aria-modal="false"
      aria-label={label}
      tabIndex={-1}
      className={`floating-popover ${actions ? 'floating-actions' : 'floating-filters'}`}
      style={{
        left: position?.left,
        top: position?.top,
        maxHeight: position?.maxHeight,
        opacity: position ? undefined : 0,
      }}
      onKeyDown={(event) => {
        if (actions && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault()
          const items = [...content.current!.querySelectorAll<HTMLElement>(FOCUSABLE)]
          const current = items.indexOf(document.activeElement as HTMLElement)
          const next =
            event.key === 'Home'
              ? 0
              : event.key === 'End'
                ? items.length - 1
                : event.key === 'ArrowDown'
                  ? (current + 1) % items.length
                  : (current - 1 + items.length) % items.length
          items[next]?.focus()
        } else if (event.key === 'Tab') {
          const items = [...panel.current!.querySelectorAll<HTMLElement>(FOCUSABLE)]
          if (event.shiftKey && document.activeElement === items[0]) {
            event.preventDefault()
            dismiss(true)
          } else if (!event.shiftKey && document.activeElement === items.at(-1)) {
            event.preventDefault()
            const outside = [...document.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
              (item) => !panel.current!.contains(item) && item.getClientRects().length > 0,
            )
            const next = outside[outside.indexOf(anchor) + 1] || anchor
            next.focus({ preventScroll: true })
            close.current()
          }
        }
      }}
    >
      <div className="floating-popover-heading">
        <span className="truncate text-sm font-semibold">{label}</span>
        <button type="button" className="action-btn" aria-label={t('Close')} onClick={() => dismiss(true)}>
          <X aria-hidden size={16} />
        </button>
      </div>
      <div
        ref={content}
        className="floating-popover-content"
        onClick={(event) => {
          const action = (event.target as Element).closest('button, a[href]')
          if (actions && action && !action.matches(':disabled')) dismiss(true)
        }}
      >
        {children}
      </div>
    </div>,
    document.body,
  )
}
