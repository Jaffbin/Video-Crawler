import { useEffect, useState } from 'react'
import { getAccess, setExtensionAccess } from '../../api/client'
import { useI18n } from '../../i18n'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

/**
 * The Chrome extension finds the app by loading its start page, which the app only serves to it when this
 * is on. Off by default, so other programs on the computer cannot do the same.
 */
export function ExtensionAccess({ onError }: { onError?: (message: string) => void }) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let stop = false
    getAccess()
      .then((result) => {
        if (!stop) setEnabled(result.extension)
      })
      .catch(() => {
        /* The setting stays hidden until the app answers. */
      })
    return () => {
      stop = true
    }
  }, [])

  if (enabled === null) return null

  async function change(next: boolean) {
    setBusy(true)
    try {
      setEnabled((await setExtensionAccess(next)).extension)
    } catch (error) {
      onError?.(error instanceof Error ? error.message : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-2">
        <label className="toggle-row min-w-0 flex-1">
          <input
            type="checkbox"
            checked={enabled}
            disabled={busy}
            onChange={(event) => void change(event.target.checked)}
          />
          <span>{t('Allow the Chrome extension to connect')}</span>
        </label>
        <HelpButton tip={tip} about={t('Allow the Chrome extension to connect')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Lets the Video Grabber Chrome extension find and connect to this app. Leave this off if you do not use it.',
        )}
      </HelpNote>
    </div>
  )
}
