import { useCallback, useState } from 'react'
import { restart } from '../api/client'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Restarting the backend creates a new random token, so this page's token stops working.
 * In a browser tab, wait until the service answers again and reload to pick up the new token.
 * (In window mode the whole window is replaced by the restarted process.)
 */
export function useRestart(onError: (message: string) => void) {
  const [restarting, setRestarting] = useState(false)

  const restartService = useCallback(async () => {
    try {
      await restart()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not restart')
      return
    }
    setRestarting(true)
    await sleep(1500)
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        const res = await fetch('/', { cache: 'no-store' })
        if (res.ok) {
          location.reload()
          return
        }
      } catch {
        /* still restarting */
      }
      await sleep(1000)
    }
    setRestarting(false)
    onError('The service did not come back. Start it again from the terminal.')
  }, [onError])

  return { restarting, restartService }
}
