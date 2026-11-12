import { FileCog } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getHooks, openHooksConfig } from '../../api/client'
import { useI18n } from '../../i18n'
import type { HookEvent, HookRun, HooksStatus } from '../../types/api'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

const EVENT_LABELS: Record<HookEvent, string> = {
  download_completed: 'After a download finishes',
  download_failed: 'After a download fails',
}

const OUTCOME_LABELS: Record<HookRun['outcome'], string> = {
  ok: 'Ran successfully',
  failed: 'Ended with an error (code {code})',
  timeout: 'Stopped: took too long',
  not_started: 'Could not start the program',
  skipped: 'Skipped: too many were waiting',
}

/** The program's own name, so long paths do not crowd the panel; the full path is in the tooltip. */
function programName(command: string[]) {
  return command[0].split(/[\\/]/).pop() || command[0]
}

/**
 * Shows which programs run after downloads. Programs are set only in the settings file, never here,
 * so nothing that shares the app's API (such as the Chrome extension) can make the app run a program.
 */
export function DownloadHooks({ onError }: { onError?: (message: string) => void }) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [status, setStatus] = useState<HooksStatus | null>(null)
  const [busy, setBusy] = useState(false)

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

  async function openSettings() {
    setBusy(true)
    try {
      setStatus(await openHooksConfig())
    } catch (error) {
      onError?.(error instanceof Error ? error.message : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }

  const configured = (Object.keys(EVENT_LABELS) as HookEvent[]).filter((event) => status.hooks[event])
  const latest = status.recent[0]
  let summary: string
  if (status.error)
    summary = t('The settings file has a problem, so nothing runs: {error}', { error: status.error })
  else if (!status.enabled || configured.length === 0) summary = t('Off. Turn it on in the settings file.')
  else summary = t('On')

  return (
    <section className="grid gap-2" aria-label={t('Run a program after downloads')}>
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">
          {t('Run a program after downloads')}
        </h3>
        <HelpButton tip={tip} about={t('Run a program after downloads')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Runs a program you choose, such as a script that moves or converts the file. Details about the download are passed to it as JSON on standard input and in VG_ environment variables. For safety, programs can only be set in the settings file, not from the app or the browser extension.',
        )}
      </HelpNote>
      <p className={status.error ? 'text-sm text-amber-300' : 'text-sm text-zinc-300'}>{summary}</p>
      {status.enabled && !status.error && configured.length > 0 && (
        <dl className="grid gap-1 text-sm">
          {configured.map((event) => {
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
        </dl>
      )}
      {latest && (
        <p className="text-sm text-zinc-400" title={latest.detail || undefined}>
          {t('Last run: {result}', {
            result: t(OUTCOME_LABELS[latest.outcome], { code: String(latest.exit_code ?? '') }),
          })}
        </p>
      )}
      <Button onClick={() => void openSettings()} disabled={busy}>
        <FileCog aria-hidden size={18} />
        {t('Open settings file')}
      </Button>
    </section>
  )
}
