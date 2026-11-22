import { useEffect, useRef, useState } from 'react'
import {
  checkYtdlp,
  getUpdateStatus,
  rollbackYtdlp,
  setTestRecentSites,
  startYtdlpUpdate,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { ComponentExtras, UpdateProbe, UpdateStatus, YtdlpCheck } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { useI18n } from '../../i18n'

interface Props {
  open: boolean
  onClose: () => void
  onRestart: () => void
  onToast: ToastFn
  /** So the header dot clears once the check is known to be current. */
  onChecked: (check: YtdlpCheck) => void
  /** Opened from "Update now": install a newer yt-dlp as soon as it is confirmed. */
  autoStart?: boolean
}

type Phase = 'idle' | 'checking' | 'installing' | 'tested' | 'needs-restart' | 'done' | 'error'

export function UpdateModal({ open, onClose, onRestart, onToast, onChecked, autoStart }: Props) {
  const { t } = useI18n()
  const [check, setCheck] = useState<YtdlpCheck | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState('')
  const [live, setLive] = useState<UpdateStatus | null>(null)
  const poller = useRef<number | undefined>(undefined)
  const started = useRef(false)

  useEffect(() => {
    if (open) void refresh(true)
    return () => window.clearTimeout(poller.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function refresh(force: boolean) {
    setPhase('checking')
    try {
      const c = await checkYtdlp(force)
      setCheck(c)
      onChecked(c)
      setPhase(c.needs_restart ? 'needs-restart' : 'idle')
      if (autoStart && c.newer && !c.needs_restart && !started.current) {
        started.current = true
        void install('default', { test: true })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t('Could not check for updates'))
      setPhase('error')
    }
  }

  async function install(extras: ComponentExtras, options: { test?: boolean; version?: string } = {}) {
    await run(() => startYtdlpUpdate(extras, options))
  }

  async function run(start: () => Promise<unknown>) {
    setPhase('installing')
    setLog([])
    setError('')
    setLive(null)
    try {
      await start()
    } catch (e) {
      setPhase('error')
      setError(e instanceof Error ? e.message : t('Could not start the update'))
      return
    }
    poll()
  }

  function poll() {
    window.clearTimeout(poller.current)
    poller.current = window.setTimeout(async () => {
      let status
      try {
        status = await getUpdateStatus()
      } catch {
        poll()
        return
      }
      setLog(status.lines)
      setLive(status)
      if (status.status === 'running') {
        poll()
        return
      }
      if (status.status === 'tested') {
        setPhase('tested')
        return
      }
      if (status.status === 'error') {
        setPhase('error')
        setError(status.error || t('Update failed'))
        return
      }
      if (status.extras.includes('deno')) {
        setPhase('needs-restart')
      } else {
        await refresh(true)
      }
    }, 800)
  }

  function probeText(probe: UpdateProbe) {
    return {
      testing: t('Testing…'),
      fine: t('Works'),
      fixed: t('Works again with the new version'),
      inconclusive: t('Could not test (link, network or sign-in)'),
      regression: t('Broken by the new version'),
    }[probe.verdict]
  }

  function probeList(probes: UpdateProbe[]) {
    return (
      <ul className="grid gap-1" aria-label={t('Sites tested')}>
        {probes.map((probe) => (
          <li key={probe.site} className="flex flex-wrap gap-x-2">
            <span className="font-medium text-zinc-100">{probe.site}</span>
            <span className={probe.verdict === 'regression' ? 'text-red-300' : 'text-zinc-400'}>
              {probeText(probe)}
            </span>
            {probe.verdict === 'regression' && probe.error && (
              <span className="w-full break-words text-xs text-zinc-500">{probe.error}</span>
            )}
          </li>
        ))}
      </ul>
    )
  }

  const target = live?.target || check?.latest || ''

  return (
    <Modal open={open} onClose={onClose} title={t('yt-dlp updates')}>
      <div className="grid gap-4 text-sm">
        {phase === 'checking' && <p className="text-zinc-400">{t('Checking…')}</p>}

        {check && phase !== 'checking' && phase !== 'installing' && (
          <div className="rounded-xl bg-white/[.03] p-3">
            <p>
              {t('Running')} <span className="font-mono">{check.running}</span>
              {/* Compare as versions: 2026.08.19 and 2026.8.19 are the same release. */}
              {check.needs_restart && (
                <>
                  {' '}
                  ({t('Installed')} <span className="font-mono">{check.installed}</span>,{' '}
                  {t('restart to use it')})
                </>
              )}
            </p>
            {check.latest && (
              <p className="mt-1 text-zinc-400">
                {t('Latest on PyPI')}: {check.latest}
              </p>
            )}
            {check.skipped && !check.newer && phase !== 'tested' && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 text-zinc-300">
                  {t('yt-dlp {version} was not installed because it broke a site in testing.', {
                    version: check.skipped,
                  })}
                </p>
                <Button onClick={() => void install('default', { version: check.skipped })}>
                  {t('Install {version} anyway', { version: check.skipped })}
                </Button>
              </div>
            )}
            {check.previous && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 text-zinc-300">
                  {t('If downloads stopped working after the last update, go back to {version}.', {
                    version: check.previous,
                  })}
                </p>
                <Button onClick={() => void run(rollbackYtdlp)}>
                  {t('Go back to {version}', { version: check.previous })}
                </Button>
              </div>
            )}
          </div>
        )}

        {phase === 'installing' && live?.phase && (
          <div className="grid gap-2 rounded-xl bg-white/[.03] p-3" role="status">
            <p>
              {live.phase === 'staging'
                ? t('Downloading yt-dlp {version} to test it…', { version: target })
                : live.phase === 'probing'
                  ? t('Testing yt-dlp {version} on {count} sites…', {
                      version: target,
                      count: live.probes?.length ?? 0,
                    })
                  : t('Tests passed. Installing yt-dlp {version}…', { version: target })}
            </p>
            {!!live.probes?.length && live.phase !== 'staging' && probeList(live.probes)}
          </div>
        )}

        {phase === 'tested' && live && (
          <div className="grid gap-3 rounded-xl bg-amber-500/[.08] p-3" role="alert">
            <p className="text-amber-100">
              {live.verdict === 'regression'
                ? t(
                    'yt-dlp {version} broke a site that works now, so your current version was kept. It will not be suggested again until a newer release appears.',
                    { version: target },
                  )
                : t(
                    'yt-dlp {version} could not be tested: no test site answered. Your current version was kept.',
                    { version: target },
                  )}
            </p>
            {!!live.probes?.length && probeList(live.probes)}
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => void refresh(true)}>
                {t('Keep current version')}
              </Button>
              <Button onClick={() => void install('default', { version: target })}>
                {t('Install {version} anyway', { version: target })}
              </Button>
            </div>
          </div>
        )}

        {phase === 'needs-restart' && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-500/[.08] p-3 text-emerald-200">
            <span>{t('Update installed. Restart the service to use it.')}</span>
            <Button variant="primary" onClick={onRestart}>
              {t('Restart service')}
            </Button>
          </div>
        )}

        {phase === 'error' && (
          <p role="alert" className="rounded-xl bg-red-500/[.08] p-3 text-red-200">
            {error}
          </p>
        )}

        {(phase === 'installing' || log.length > 0) && (
          <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-black/40 p-3 font-mono text-xs text-zinc-300">
            {log.join('\n') || t('Starting…')}
          </pre>
        )}

        {check?.newer && phase !== 'installing' && (
          <label className="flex items-start gap-2 text-zinc-300">
            <input
              type="checkbox"
              className="mt-1"
              checked={check.test_recent_sites === true}
              onChange={async (event) => {
                const enabled = event.target.checked
                try {
                  const saved = await setTestRecentSites(enabled)
                  setCheck({ ...check, test_recent_sites: saved.test_recent_sites })
                } catch {
                  onToast(t('That did not work'), true)
                }
              }}
            />
            <span>
              {t(
                'Also test on up to three sites you downloaded from recently. This opens one recent link per site again, without cookies.',
              )}
            </span>
          </label>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => refresh(true)} disabled={phase === 'checking' || phase === 'installing'}>
            {t('Check again')}
          </Button>
          <Button
            variant="primary"
            disabled={phase === 'installing' || phase === 'checking'}
            onClick={() => void (check?.newer ? install('default', { test: true }) : install('default,deno'))}
          >
            {check?.newer ? t('Test and update yt-dlp') : t('Install YouTube components')}
          </Button>
          {check?.newer && (
            <Button
              variant="ghost"
              disabled={phase === 'installing' || phase === 'checking'}
              onClick={() => void install('default')}
            >
              {t('Update without testing')}
            </Button>
          )}
          <Button
            variant="ghost"
            disabled={phase === 'installing'}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText('pip install -U "yt-dlp[default,deno]"')
                onToast(t('Command copied'))
              } catch {
                onToast(t('Could not copy'), true)
              }
            }}
          >
            {t('Copy command')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
