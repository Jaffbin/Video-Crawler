import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

export function CloseBehavior({
  settingsOpen,
  onCloseSettings,
  pendingDownloads = 0,
}: {
  settingsOpen: boolean
  onCloseSettings: () => void
  pendingDownloads?: number
}) {
  const { t } = useI18n()
  const [prompt, setPrompt] = useState(false)
  const [remember, setRemember] = useState(false)
  const [behavior, setBehavior] = useState<'ask' | 'background' | 'exit'>('ask')
  const [trayReady, setTrayReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(pendingDownloads)
  useEffect(() => setPending(pendingDownloads), [pendingDownloads])
  useEffect(() => {
    if (!prompt || !window.pywebview?.api.close_settings) return
    const timer = window.setInterval(() => {
      void window.pywebview?.api
        .close_settings?.()
        .then((value) => {
          if (typeof value.pending_downloads === 'number') setPending(value.pending_downloads)
          setTrayReady(value.tray_ready)
        })
        .catch(() => undefined)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [prompt])

  useEffect(() => {
    const sync = () => {
      void window.pywebview?.api
        .close_settings?.()
        .then((value) => {
          setBehavior(value.behavior)
          setTrayReady(value.tray_ready)
          if (typeof value.pending_downloads === 'number') setPending(value.pending_downloads)
        })
        .catch(() => setError(t('Could not load close settings.')))
    }
    const request = (event: Event) => {
      event.preventDefault()
      sync()
      setRemember(false)
      setError('')
      setPrompt(true)
    }
    sync()
    window.addEventListener('pywebviewready', sync)
    window.addEventListener('grab-close-request', request)
    return () => {
      window.removeEventListener('pywebviewready', sync)
      window.removeEventListener('grab-close-request', request)
    }
  }, [t, settingsOpen])

  async function act(action: 'cancel' | 'background' | 'exit') {
    setBusy(true)
    setError('')
    try {
      await window.pywebview?.api.close_action?.(action, action === 'background' && remember)
      if (action === 'background' && remember) setBehavior('background')
      setPrompt(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Could not change close behavior.'))
    } finally {
      setBusy(false)
    }
  }

  async function save() {
    setBusy(true)
    setError('')
    try {
      await window.pywebview?.api.set_close_behavior?.(behavior)
      onCloseSettings()
    } catch {
      setError(t('Could not change close behavior.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Modal
        open={settingsOpen && !prompt}
        title={t('Close behavior')}
        onClose={() => {
          if (!busy) onCloseSettings()
        }}
      >
        <div className="grid gap-4">
          <label className="control">
            <span>{t('When closing the main window')}</span>
            <select
              className="field"
              value={behavior}
              disabled={busy}
              onChange={(e) => setBehavior(e.target.value as 'ask' | 'background' | 'exit')}
            >
              <option value="ask">{t('Ask every time')}</option>
              <option value="background">{t('Always run in background')}</option>
              <option value="exit">{t('Exit directly')}</option>
            </select>
          </label>
          {behavior === 'exit' && (
            <p className="text-sm text-zinc-400">
              {t('Unfinished downloads still require confirmation, including paused waiting tasks.')}
            </p>
          )}
          <p className="text-sm text-zinc-400">{t('Use Exit in the tray menu to fully close the app.')}</p>
          {error && <p role="alert">{error}</p>}
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            {t('Save')}
          </Button>
        </div>
      </Modal>
      <Modal
        open={prompt}
        title={t('Close Video Grabber?')}
        onClose={() => {
          if (!busy) void act('cancel')
        }}
      >
        <div className="grid gap-4">
          <p role="status" className="font-semibold">
            {pending > 0
              ? t('Unfinished downloads: {count}', { count: pending })
              : t('No unfinished downloads.')}
          </p>
          <p className="text-sm text-zinc-400">
            {t('Background keeps downloads running. Exit stops the app and unfinished downloads.')}
          </p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={remember}
              disabled={busy}
              onChange={(event) => setRemember(event.target.checked)}
            />
            {t('Always run in background')}
          </label>
          {!trayReady && (
            <p role="alert">{t('The tray is unavailable. Keep the window open or exit the app.')}</p>
          )}
          {error && <p role="alert">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={busy || !trayReady} onClick={() => void act('background')}>
              {t('Run in background')}
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void act('exit')}>
              {t('Exit app')}
            </Button>
            <Button disabled={busy} onClick={() => void act('cancel')}>
              {t('Cancel')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
