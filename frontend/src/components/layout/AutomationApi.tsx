import { Copy, KeyRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { changeAutomationApi, getAutomationApi, type AutomationApiStatus } from '../../api/client'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

/**
 * Lets other programs on this computer queue downloads. Off by default; its token is shown once.
 * Hidden in clients that may not manage it (such as the Chrome extension).
 */
export function AutomationApi({ onError }: { onError?: (message: string) => void }) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [status, setStatus] = useState<AutomationApiStatus | null>(null)
  const [token, setToken] = useState('')
  const [copied, setCopied] = useState(false)
  const [confirmNew, setConfirmNew] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let stop = false
    getAutomationApi()
      .then((result) => {
        if (!stop) setStatus(result)
      })
      .catch(() => {
        /* Stays hidden when the app does not answer or this client may not manage the API. */
      })
    return () => {
      stop = true
    }
  }, [])

  if (status === null) return null

  async function change(action: 'enable' | 'disable' | 'new_token') {
    setBusy(true)
    try {
      const result = await changeAutomationApi(action)
      setStatus(result)
      setConfirmNew(false)
      setCopied(false)
      setToken(result.token ?? (action === 'disable' ? '' : token))
    } catch (error) {
      onError?.(error instanceof Error ? error.message : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
    } catch {
      onError?.(t('Could not copy. Select the token and copy it yourself.'))
    }
  }

  return (
    <section className="grid gap-2" aria-label={t('Automation API')}>
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">{t('Automation API')}</h3>
        <HelpButton tip={tip} about={t('Automation API')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Lets programs on this computer, such as scripts or n8n, add downloads and check their progress. They can only choose the format and quality; cookies, proxies, folders and your Library stay out of reach. Programs on other devices cannot connect.',
        )}
      </HelpNote>
      <p className="text-sm text-zinc-300">
        {status.enabled
          ? t('On. Address: {url}', { url: status.base_url })
          : t('Off. Other programs cannot add downloads.')}
      </p>
      {token && (
        <div className="grid gap-2 rounded-xl bg-amber-500/[.08] p-3" role="status">
          <p className="text-sm text-amber-100">{t('Copy this token now. It will not be shown again.')}</p>
          <div className="flex min-w-0 items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded-lg bg-black/30 px-2 py-1 text-xs text-zinc-100">
              {token}
            </code>
            <Button onClick={() => void copy()} aria-label={t('Copy token')}>
              <Copy aria-hidden size={14} />
              {t(copied ? 'Copied' : 'Copy')}
            </Button>
          </div>
        </div>
      )}
      {confirmNew ? (
        <div className="grid gap-2 rounded-xl bg-white/5 p-3">
          <p className="text-sm">
            {t('Programs using the current token will stop working until you give them the new one.')}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setConfirmNew(false)}>
              {t('Cancel')}
            </Button>
            <Button variant="primary" disabled={busy} onClick={() => void change('new_token')}>
              {t('Replace token')}
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          <Button disabled={busy} onClick={() => void change(status.enabled ? 'disable' : 'enable')}>
            {t(status.enabled ? 'Turn off the API' : 'Turn on the API')}
          </Button>
          {status.has_token && (
            <Button disabled={busy} onClick={() => setConfirmNew(true)}>
              <KeyRound aria-hidden size={14} />
              {t('Create a new token')}
            </Button>
          )}
        </div>
      )}
    </section>
  )
}
