import { useEffect, useRef } from 'react'
import { notifyDesktop } from '../api/client'
import type { Job } from '../types/api'
import { completionMessage, emptyBatch, type Batch } from '../lib/completion'

const BASE_TITLE = 'Video Grabber'

interface Options {
  /** In window mode the backend shows native notifications, so the browser API is not used. */
  serverNotifies: boolean
  onAnnounce: (message: string, allFailed: boolean) => void
}

/**
 * Announce once when the whole queue becomes idle ("3 downloads completed"), not once per file.
 * Also keeps the tab title informative. Runs on every jobs update; polling continues in the background.
 */
export function useCompletionNotifier(jobs: Job[], { serverNotifies, onAnnounce }: Options) {
  const lastStatus = useRef(new Map<string, string>())
  const wasActive = useRef(false)
  const batch = useRef<Batch>(emptyBatch())
  const doneMark = useRef(false)
  const announce = useRef(onAnnounce)
  announce.current = onAnnounce

  useEffect(() => {
    const reset = () => {
      doneMark.current = false
      if (!document.hidden) document.title = BASE_TITLE
    }
    window.addEventListener('focus', reset)
    return () => window.removeEventListener('focus', reset)
  }, [])

  useEffect(() => {
    let active = 0
    for (const job of jobs) {
      const before = lastStatus.current.get(job.id)
      const wasWorking = before === 'queued' || before === 'running'
      if (wasWorking && job.status === 'done') {
        batch.current.ok++
        batch.current.title = job.title || job.url
      }
      if (wasWorking && job.status === 'error') batch.current.bad++
      lastStatus.current.set(job.id, job.status)
      if (job.status === 'queued' || job.status === 'running') active++
    }

    if (wasActive.current && active === 0 && batch.current.ok + batch.current.bad > 0) {
      const message = completionMessage(batch.current)
      const allFailed = batch.current.ok === 0
      batch.current = emptyBatch()
      const away = document.hidden || !document.hasFocus()
      if (away) doneMark.current = true
      announce.current(message, allFailed)
      if (away && serverNotifies) {
        notifyDesktop(BASE_TITLE, message).catch(() => {
          /* the platform's native notifier is unavailable; the in-app toast already fired */
        })
      } else if (away && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        try {
          const n = new Notification(BASE_TITLE, { body: message, tag: 'grab-done' })
          n.onclick = () => {
            window.focus()
            n.close()
          }
        } catch {
          /* some browsers only allow notifications from a service worker */
        }
      }
    }
    wasActive.current = active > 0

    document.title = active
      ? `Downloading (${active}) - ${BASE_TITLE}`
      : doneMark.current
        ? `Done - ${BASE_TITLE}`
        : BASE_TITLE
  }, [jobs, serverNotifies])
}
