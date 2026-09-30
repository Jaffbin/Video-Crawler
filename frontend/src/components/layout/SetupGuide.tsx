import { useState } from 'react'
import { getDoctor } from '../../api/client'
import { useI18n } from '../../i18n'
import type { DoctorResult } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const CORE_CHECKS = ['ffmpeg', 'ytdlp', 'js_runtime', 'ejs', 'impersonation', 'pywebview']

export function SetupGuide({
  open,
  doctor,
  onClose,
  onDiagnostics,
  onStart,
}: {
  open: boolean
  doctor: DoctorResult | null
  onClose: () => void
  onDiagnostics: () => void
  onStart: () => void
}) {
  const { t } = useI18n()
  const [network, setNetwork] = useState<DoctorResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const checks = (network ?? doctor)?.checks?.filter((check) => CORE_CHECKS.includes(check.id)) ?? []
  const networkChecks = network?.checks?.filter((check) => check.id.startsWith('net_')) ?? []

  async function testNetwork() {
    setBusy(true)
    setError('')
    try {
      setNetwork(await getDoctor(true, true))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Network test failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t('Welcome to Video Grabber')} wide>
      <div className="grid gap-5 text-sm">
        <p className="text-zinc-300">
          {t('Check the local components, test connectivity, then paste a video link to begin.')}
        </p>
        <section>
          <h3 className="mb-2 font-medium">{t('Component check')}</h3>
          {checks.length ? (
            <ul className="grid gap-2 sm:grid-cols-2">
              {checks.map((check) => (
                <li key={check.id} className="flex items-center gap-2 rounded-lg bg-white/[.035] px-3 py-2">
                  <span
                    aria-label={t(check.status)}
                    className={
                      check.status === 'ok'
                        ? 'text-emerald-300'
                        : check.status === 'info'
                          ? 'text-zinc-400'
                          : 'text-amber-300'
                    }
                  >
                    {check.status === 'ok' ? '✓' : check.status === 'info' ? '·' : '!'}
                  </span>
                  <span>{t(`check.${check.id}`)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-zinc-400">{t('Checking…')}</p>
          )}
        </section>
        <section className="grid gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="font-medium">{t('Network check')}</h3>
            <Button onClick={testNetwork} disabled={busy}>
              {busy ? t('Testing…') : t('Test network')}
            </Button>
          </div>
          <p className="text-xs text-zinc-400">
            {t(
              'If a site cannot be reached, the network test helps distinguish DNS and proxy problems. It does not change system settings.',
            )}
          </p>
          {error && (
            <p role="alert" className="text-red-300">
              {error}
            </p>
          )}
          {network && (
            <div className="grid gap-2 text-xs text-zinc-300">
              <p>
                {t('Network checks completed: {count}', { count: networkChecks.length })}.{' '}
                {t('Open Diagnostics for details.')}
              </p>
              <ul className="flex flex-wrap gap-2">
                {networkChecks.map((check) => (
                  <li
                    key={check.id}
                    className={`rounded-lg px-2 py-1 ${check.status === 'ok' ? 'bg-emerald-500/10 text-emerald-200' : 'bg-amber-500/10 text-amber-200'}`}
                  >
                    {check.label}: {t(check.status)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
        <div className="flex flex-wrap justify-end gap-2 border-t border-white/[.07] pt-4">
          <Button variant="ghost" onClick={onDiagnostics}>
            {t('Open Diagnostics')}
          </Button>
          <Button variant="primary" onClick={onStart}>
            {t('Start downloading')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
