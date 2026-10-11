import { useCallback, useState } from 'react'

export interface ToastItem {
  id: number
  message: string
  error: boolean
  action?: ToastAction
}

export interface ToastAction {
  label: string
  onClick: () => Promise<void>
}

export type ToastFn = (message: string, error?: boolean, action?: ToastAction) => void

let counter = 0

export function useToasts(durationMs = 4500) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const remove = useCallback((id: number) => setToasts((items) => items.filter((t) => t.id !== id)), [])

  const push: ToastFn = useCallback(
    (message, error = false, action) => {
      const id = ++counter
      setToasts((items) => [...items, { id, message, error, action }])
      // Undo remains available until used or dismissed, including after a failed restore.
      if (!action) window.setTimeout(() => remove(id), durationMs)
    },
    [remove, durationMs],
  )

  return { toasts, push, remove }
}
