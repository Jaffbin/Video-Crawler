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
  onLibrary,
  onPrepare,
  preparing = false,
  preparationStage = 'checking',
}: {
  open: boolean
  doctor: DoctorResult | null
  onClose: () => void
  onDiagnostics: () => void
  onStart: (imagesOnly?: boolean) => void
  onLibrary?: () => void
  onPrepare?: () => Promise<void>
  preparing?: boolean
  preparationStage?: string
}) {
  const { t } = useI18n()
  const [capability, setCapability] = useState<Awaited<ReturnType<typeof getSetupStatus>> | null>(null)
  const [error, setError] = useState('')
  const [checkFailed, setCheckFailed] = useState(false)
  const [checkAttempt, setCheckAttempt] = useState(0)
  const checks = doctor?.checks?.filter((check) => REQUIRED.includes(check.id)) ?? []
  const issues = checks.filter((check) => check.status === 'error' || check.status === 'warn')
  const ready = doctor !== null && issues.length === 0
  const blocked = capability?.blocked || issues.some((check) => check.detail.includes('WinError 4551'))
  const stages: Record<string, string> = {
    checking: 'Checking what is needed…',
    media: 'Preparing video and audio tools…',
    sites: 'Preparing website support…',
    verifying: 'Making sure everything works…',
    ready: 'Preparation complete. Restarting if needed…',
  }
  useEffect(() => {
    if (!open) return
    let active = true
    setError('')
    setCheckFailed(false)
    void getSetupStatus()
      .then((result) => {
        if (active) setCapability(result)
      })
      .catch(() => {
        if (active) setCheckFailed(true)
      })
    return () => {
      active = false
    }
  }, [open, doctor, checkAttempt])
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
        <ol
          aria-label={t('Getting started steps')}
          className="grid gap-2 text-xs text-zinc-400 sm:grid-cols-3"
        >
          {['Check and prepare', 'Paste your first link', 'Find files in Library'].map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              <span
                aria-hidden
                className="grid size-6 shrink-0 place-items-center rounded-full bg-white/[.08] font-semibold"
              >
                {index + 1}
              </span>
              {t(step)}
            </li>
          ))}
        </ol>
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
          {preparing && (
            <p className="mt-3 font-medium" aria-live="polite">
              {t(stages[preparationStage] || stages.checking)}
            </p>
          )}
          {preparing && (
            <p className="mt-2 text-xs text-zinc-400">
              {t(
                'Keep the app open. Needed components are downloaded automatically; this may take a few minutes.',
              )}
            </p>
          )}
        </div>
        {!ready && doctor && !blocked && capability?.can_install === true && onPrepare && (
          <Button variant="primary" disabled={preparing} onClick={prepare}>
            {t(preparing ? 'Preparing…' : error ? 'Try preparation again' : 'Prepare download features')}
          </Button>
        )}
        {checkFailed && !preparing && (
          <div role="alert" className="grid gap-2">
            <p>{t('Could not check preparation. Check your connection to the app and try again.')}</p>
            <Button onClick={() => setCheckAttempt((attempt) => attempt + 1)}>{t('Check again')}</Button>
          </div>
        )}
        {!ready && capability?.can_install === false && !blocked && (
          <p className="text-zinc-400">
            {t('Automatic preparation is available in the Windows app. You can still download images here.')}
          </p>
        )}
        <p className="text-zinc-400">
          {t(
            'Copy a video or music page link from your browser. The next screen lets you paste it and choose video, audio or images.',
          )}
        </p>
        <p className="text-zinc-400">
          {t('Finished downloads are easy to play or preview. Find them anytime in Library.')}
        </p>
        {error && (
          <p role="alert" className="text-red-300">
            {error}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2 border-t border-white/[.07] pt-4">
          {onLibrary && (
            <Button disabled={preparing} onClick={onLibrary}>
              {t('Open Library')}
            </Button>
          )}
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
