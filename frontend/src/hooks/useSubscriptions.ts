import { useCallback, useEffect, useRef, useState } from 'react'
import { getSubscriptions } from '../api/client'
import type { Subscription } from '../types/api'

const POLL_MS = 8000 // subscriptions change far less often than jobs, so this polls independently and slower

export function useSubscriptions() {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [intervalSeconds, setIntervalSeconds] = useState(3600)
  const poll = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    let stopped = false
    let timer: number | undefined

    const load = async () => {
      try {
        const res = await getSubscriptions()
        if (stopped) return
        setSubscriptions(res.subscriptions ?? [])
        setIntervalSeconds(res.interval_seconds ?? 3600)
      } catch {
        /* the header/queue polling already surfaces connection loss */
      }
    }
    poll.current = load

    const loop = async () => {
      await load()
      if (!stopped) timer = window.setTimeout(loop, document.hidden ? POLL_MS * 3 : POLL_MS)
    }
    void loop()

    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [])

  const refresh = useCallback(() => poll.current(), [])
  return { subscriptions, intervalSeconds, refresh }
}
