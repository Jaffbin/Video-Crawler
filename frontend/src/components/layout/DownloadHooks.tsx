import { FileCog, Send } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getHooks, openHooksConfig, testNotifications } from '../../api/client'
import { useI18n } from '../../i18n'
import type {
  HookEvent,
  HookRun,
  HooksStatus,
  NotificationTestResponse,
  NotificationType,
} from '../../types/api'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

const EVENTS: HookEvent[] = ['download_completed', 'download_failed']

const EVENT_LABELS: Record<HookEvent, string> = {
  download_completed: 'After a download finishes',
  download_failed: 'After a download fails',
}

const ONLY_LABELS: Record<HookEvent, string> = {
  download_completed: 'finished downloads only',
  download_failed: 'failed downloads only',
}

const CHANNEL_NAMES: Record<NotificationType, string> = {
  discord: 'Discord',
  telegram: 'Telegram',
  ntfy: 'ntfy',
  webhook: 'Webhook',
}

const PROGRAM_OUTCOMES: Record<HookRun['outcome'], string> = {
  ok: 'Ran successfully',
  failed: 'Ended with an error (code {code})',
  timeout: 'Stopped: took too long',
  not_started: 'Could not start the program',
  skipped: 'Skipped: too many were waiting',
}

const NOTIFICATION_OUTCOMES: Record<HookRun['outcome'], string> = {
  ok: 'Sent',
  failed: 'Not sent',
  timeout: 'Not sent',
  not_started: 'Not sent',
  skipped: 'Skipped: too many were waiting',
}

/** The program's own name, so long paths do not crowd the panel; the full path is in the tooltip. */
function programName(command: string[]) {
  return command[0].split(/[\\/]/).pop() || command[0]
}

/**
 * Shows what happens after downloads. Programs and notification addresses are set only in the
 * settings file, never here, so nothing that shares the app's API (such as the Chrome extension)
 * can make the app run a program or send messages somewhere else.
 */
export function DownloadHooks({ onError }: { onError?: (message: string) => void }) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [status, setStatus] = useState<HooksStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [test, setTest] = useState<NotificationTestResponse['results'] | null>(null)

  useEffect(() => {
    let stop = false
    getHooks()
      .then((result) => {
        if (!stop) setStatus(result)
      })
      .catch(() => {
        /* Hidden when the app does not answer, or in clients that may not see hook settings. */
      })
    return () => {
      stop = true
    }
  }, [])

  if (status === null) return null

  async function run(action: () => Promise<void>) {
    setBusy(true)
    try {
      await action()
    } catch (error) {
      onError?.(error instanceof Error ? error.message : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }

  const openSettings = () =>
    run(async () => {
      setStatus(await openHooksConfig())
    })

  const sendTest = () =>
    run(async () => {
      setTest(null)
      const response = await testNotifications()
      setStatus(response.status)
      setTest(response.results)
    })

  const programs = EVENTS.filter((event) => status.hooks[event])
  const channels = status.notifications ?? []
  const active = status.enabled && !status.error && (programs.length > 0 || channels.length > 0)
  // Testing works while turned off, so channels can be checked before they go live.
  const canTest = channels.length > 0 && !status.error
  let summary: string
  if (status.error)
    summary = t('The settings file has a problem, so nothing runs: {error}', { error: status.error })
  else if (!active) summary = t('Off. Turn it on in the settings file.')
  else summary = t('On')

  const lastProgram = status.recent.find((item) => item.kind !== 'notification')
  const lastNotification = status.recent.find((item) => item.kind === 'notification')
  const sent = test?.filter((item) => item.ok).length ?? 0

  return (
    <section className="grid gap-2" aria-label={t('After downloads')}>
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">{t('After downloads')}</h3>
        <HelpButton tip={tip} about={t('After downloads')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Run a program you choose, such as a script that moves or converts the file, and send a message to Discord, Telegram, ntfy or your own web address. For safety, these can only be set in the settings file, not from the app or the browser extension.',
        )}
      </HelpNote>
      <p className={status.error ? 'text-sm text-amber-300' : 'text-sm text-zinc-300'}>{summary}</p>
      {active && (
        <dl className="grid gap-1 text-sm">
          {programs.map((event) => {
            const command = status.hooks[event]!.command
            return (
              <div key={event} className="flex min-w-0 flex-wrap gap-x-2">
                <dt className="text-zinc-400">{t(EVENT_LABELS[event])}</dt>
                <dd className="min-w-0 truncate text-zinc-100" title={command.join(' ')}>
                  {programName(command)}
                </dd>
              </div>
            )
          })}
          {channels.map((channel, index) => (
            <div key={index} className="flex min-w-0 flex-wrap gap-x-2">
              <dt className="text-zinc-400">{t('Notify')}</dt>
              <dd className="min-w-0 truncate text-zinc-100">
                {CHANNEL_NAMES[channel.type]} ({channel.target})
                {channel.events.length === 1 && (
                  <span className="text-zinc-400">, {t(ONLY_LABELS[channel.events[0]])}</span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {lastProgram && (
        <p className="text-sm text-zinc-400" title={lastProgram.detail || undefined}>
          {t('Last run: {result}', {
            result: t(PROGRAM_OUTCOMES[lastProgram.outcome], {
              code: String(lastProgram.exit_code ?? ''),
            }),
          })}
        </p>
      )}
      {lastNotification && (
        <p className="text-sm text-zinc-400" title={lastNotification.detail || undefined}>
          {t('Last notification to {target}: {result}', {
            target: lastNotification.target,
            result: t(NOTIFICATION_OUTCOMES[lastNotification.outcome]),
          })}
        </p>
      )}
      {test && (
        <div role="status" className="grid gap-1 text-sm">
          <p className={sent === test.length ? 'text-zinc-300' : 'text-amber-300'}>
            {t('Test sent to {sent} of {total}.', { sent, total: test.length })}
          </p>
          {test
            .filter((item) => !item.ok)
            .map((item, index) => (
              <p key={index} className="text-amber-300">
                {item.target}: {item.detail}
              </p>
            ))}
        </div>
      )}
      <div className={canTest ? 'grid gap-2 sm:grid-cols-2' : 'grid gap-2'}>
        <Button onClick={() => void openSettings()} disabled={busy}>
          <FileCog aria-hidden size={18} />
          {t('Open settings file')}
        </Button>
        {canTest && (
          <Button onClick={() => void sendTest()} disabled={busy}>
            <Send aria-hidden size={18} />
            {t('Send a test notification')}
          </Button>
        )}
      </div>
    </section>
  )
}
