import { useCallback, useState } from 'react'

export interface ToastItem {
  id: number
  message: string
  error: boolean
}

export type ToastFn = (message: string, error?: boolean) => void

let counter = 0

export function useToasts(durationMs = 4500) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const remove = useCallback((id: number) => setToasts((items) => items.filter((t) => t.id !== id)), [])

  const push: ToastFn = useCallback(
    (message, error = false) => {
      const id = ++counter
      setToasts((items) => [...items, { id, message, error }])
      window.setTimeout(() => remove(id), durationMs)
    },
    [remove, durationMs],
  )

  return { toasts, push, remove }
}
