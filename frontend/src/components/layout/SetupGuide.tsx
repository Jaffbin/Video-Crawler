import { useEffect, useState } from 'react'
import { getSetupStatus } from '../../api/client'
import { useI18n } from '../../i18n'
import type { DoctorResult } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const REQUIRED = ['python', 'ytdlp', 'ffmpeg', 'ffprobe', 'js_runtime', 'ejs', 'impersonation']

export function SetupGuide({
  open,
  doctor,
  onClose,
  onDiagnostics,
  onStart,
  onPrepare,
  preparing = false,
}: {
  open: boolean
  doctor: DoctorResult | null
  onClose: () => void
  onDiagnostics: () => void
  onStart: (imagesOnly?: boolean) => void
  onPrepare?: () => Promise<void>
  preparing?: boolean
}) {
  const { t } = useI18n()
  const [capability, setCapability] = useState<Awaited<ReturnType<typeof getSetupStatus>> | null>(null)
  const [error, setError] = useState('')
  const checks = doctor?.checks?.filter((check) => REQUIRED.includes(check.id)) ?? []
  const issues = checks.filter((check) => check.status === 'error' || check.status === 'warn')
  const ready = doctor !== null && issues.length === 0
  const blocked = capability?.blocked || issues.some((check) => check.detail.includes('WinError 4551'))
  useEffect(() => {
    if (!open) return
    let active = true
    setError('')
    void getSetupStatus()
      .then((result) => {
        if (active) setCapability(result)
      })
      .catch(() => {
        /* component checks still show the current readiness */
      })
    return () => {
      active = false
    }
  }, [open, doctor])
  async function prepare() {
    setError('')
    try {
      await onPrepare?.()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'Preparation failed. Check your connection and try again.'))
    }
  }
  return (
    <Modal
      open={open}
      onClose={() => {
        if (!preparing) onClose()
      }}
      title={t('Welcome to Video Grabber')}
    >
      <div className="grid gap-5 text-sm">
        <div role="status" className="rounded-xl bg-white/[.04] p-4">
          <h3 className="text-lg font-semibold">
            {t(
              preparing
                ? 'Preparing download features…'
                : !doctor
                  ? 'Checking download features…'
                  : ready
                    ? 'Ready to download'
                    : blocked
                      ? 'Windows blocked a download feature.'
                      : 'A few download features need preparation.',
            )}
          </h3>
          <p className="mt-2 text-zinc-400">
            {t(
              ready
                ? 'Paste a link, choose what to save, and start downloading.'
                : blocked
                  ? 'The app cannot change this Windows security decision. Technical details show which file was blocked.'
                  : 'We handle the required tools for you. No paths or commands to enter.',
            )}
          </p>
        </div>
        {!ready && doctor && !blocked && capability?.can_install !== false && onPrepare && (
          <Button variant="primary" disabled={preparing} onClick={prepare}>
            {t(preparing ? 'Preparing…' : 'Prepare download features')}
          </Button>
        )}
        {!ready && capability?.can_install === false && !blocked && (
          <p className="text-zinc-400">
            {t('Automatic preparation is available in the Windows app. You can still download images here.')}
          </p>
        )}
        <p className="text-zinc-400">
          {t('Finished downloads are easy to play or preview. Find them anytime in Library.')}
        </p>
        {error && (
          <p role="alert" className="text-red-300">
            {error}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2 border-t border-white/[.07] pt-4">
          <Button variant="ghost" disabled={preparing} onClick={onDiagnostics}>
            {t('Technical details')}
          </Button>
          <Button
            variant={ready ? 'primary' : 'default'}
            disabled={preparing || !doctor}
            onClick={() => onStart(!ready)}
          >
            {t(ready ? 'Start downloading' : 'Download images for now')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
