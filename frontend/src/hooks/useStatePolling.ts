import { useCallback, useEffect, useRef, useState } from 'react'
import { getState } from '../api/client'
import type { StateResponse } from '../types/api'

const EMPTY: StateResponse = {
  version: '—',
  ffmpeg: true,
  playwright: false,
  root: '',
  rev: -1,
  jobs: [],
  files: [],
  desktop_notifications: false,
  window: false,
}

export const VISIBLE_INTERVAL_MS = 1000
/** Never stop polling while the tab is hidden: that is exactly when "downloads finished" matters. */
export const HIDDEN_INTERVAL_MS = 4000

export function useStatePolling() {
  const rev = useRef(-1)
  const pollNow = useRef<() => Promise<void>>(async () => {})
  const [state, setState] = useState<StateResponse>(EMPTY)
  const [online, setOnline] = useState(true)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const next = await getState(rev.current)
        if (stopped) return
        rev.current = next.rev
        // The backend only sends "files" when they changed, so keep the previous list otherwise.
        setState((prev) => ({ ...prev, ...next, files: next.files ?? prev.files }))
        setOnline(true)
      } catch {
        if (!stopped) setOnline(false)
      }
    }
    pollNow.current = poll

    const loop = async () => {
      await poll()
      if (!stopped)
        timer = window.setTimeout(loop, document.hidden ? HIDDEN_INTERVAL_MS : VISIBLE_INTERVAL_MS)
    }
    void loop()

    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [])

  /** Fetch again right away (after adding, cancelling, removing...). */
  const refresh = useCallback(() => pollNow.current(), [])
  /** Also re-scan the download folder for files changed outside the app. */
  const refreshFiles = useCallback(() => {
    rev.current = -1
    return pollNow.current()
  }, [])

  return { state, online, refresh, refreshFiles }
}
