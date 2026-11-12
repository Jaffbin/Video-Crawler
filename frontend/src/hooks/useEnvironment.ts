import { useCallback, useEffect, useState } from 'react'
import { checkYtdlp, getDoctor } from '../api/client'
import type { DoctorCheck, DoctorResult, YtdlpCheck } from '../types/api'

const DISMISS_KEY = 'grab-env-dismissed'
const UPDATE_DISMISS_KEY = 'grab-update-dismissed'
/** The two things YouTube needs on top of yt-dlp itself. ffmpeg has its own banner. */
const YOUTUBE_CHECKS = ['js_runtime', 'ejs']

export function youtubeIssues(doctor: DoctorResult | null): DoctorCheck[] {
  return (doctor?.checks ?? []).filter(
    (c) => YOUTUBE_CHECKS.includes(c.id) && (c.status === 'warn' || c.status === 'error'),
  )
}

export function issueSignature(issues: DoctorCheck[]): string {
  return issues.map((c) => c.id).join(',')
}

function readDismissed(key = DISMISS_KEY): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

/** A quiet background check on load, so the header and banner can point at problems early. */
export function useEnvironment() {
  const [doctor, setDoctor] = useState<DoctorResult | null>(null)
  const [update, setUpdate] = useState<YtdlpCheck | null>(null)
  const [dismissed, setDismissed] = useState(() => readDismissed())
  const [dismissedUpdate, setDismissedUpdate] = useState(() => readDismissed(UPDATE_DISMISS_KEY))

  const refresh = useCallback(async () => {
    const [d, u] = await Promise.allSettled([getDoctor(false, false), checkYtdlp(false)])
    if (d.status === 'fulfilled') setDoctor(d.value)
    if (u.status === 'fulfilled') setUpdate(u.value)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const issues = youtubeIssues(doctor)
  const signature = issueSignature(issues)
  const showBanner = issues.length > 0 && dismissed !== signature

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(DISMISS_KEY, signature)
    } catch {
      /* ignore */
    }
    setDismissed(signature)
  }, [signature])

  // The banner returns when a still newer version is released.
  const newVersion = update?.newer && update.latest ? update.latest : null
  const updateVersion = newVersion && newVersion !== dismissedUpdate ? newVersion : null
  const dismissUpdate = useCallback(() => {
    if (!newVersion) return
    try {
      localStorage.setItem(UPDATE_DISMISS_KEY, newVersion)
    } catch {
      /* ignore */
    }
    setDismissedUpdate(newVersion)
  }, [newVersion])

  return { doctor, update, issues, showBanner, dismiss, refresh, updateVersion, dismissUpdate }
}
