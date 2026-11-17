import { useEffect, useState } from 'react'
import { getMediaExport, setMediaExportFolder } from '../../api/client'
import { useI18n } from '../../i18n'
import type { MediaExportStatus } from '../../types/api'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

/**
 * Where videos are placed for Jellyfin, Plex, Emby or Kodi. Hidden in clients that may not change it
 * (such as the Chrome extension), because it decides where the app writes files.
 */
export function MediaExportSettings({ onError }: { onError?: (message: string) => void }) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [status, setStatus] = useState<MediaExportStatus | null>(null)
  const [folder, setFolder] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let stop = false
    getMediaExport()
      .then((result) => {
        if (stop) return
        setStatus(result)
        setFolder(result.folder)
      })
      .catch(() => {
        /* Stays hidden when the app does not answer or this client may not change it. */
      })
    return () => {
      stop = true
    }
  }, [])

  if (status === null) return null

  async function save(value: string) {
    setBusy(true)
    setError('')
    try {
      const result = await setMediaExportFolder(value)
      setStatus(result)
      setFolder(result.folder)
    } catch (reason) {
      const message = t(reason instanceof Error ? reason.message : 'That did not work')
      setError(message)
      onError?.(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="grid gap-2" aria-label={t('Media server folder')}>
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">{t('Media server folder')}</h3>
        <HelpButton tip={tip} about={t('Media server folder')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Videos are arranged by channel and year with titles, descriptions, covers and subtitles that Jellyfin, Plex, Emby and Kodi read. On the same disk they are hard-linked and use no extra space; on another disk they are copied. Nothing there is overwritten or deleted.',
        )}
      </HelpNote>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void save(folder)
        }}
      >
        <label className="min-w-0 flex-1 basis-56">
          <span className="sr-only">{t('Media server folder')}</span>
          <input
            className="field"
            placeholder="D:\\Media\\YouTube"
            spellCheck={false}
            value={folder}
            disabled={busy}
            onChange={(event) => setFolder(event.target.value)}
          />
        </label>
        <Button type="submit" disabled={busy || folder.trim() === status.folder}>
          {t('Save')}
        </Button>
        {status.folder && (
          <Button disabled={busy} onClick={() => void save('')}>
            {t('Turn off')}
          </Button>
        )}
      </form>
      <p className={status.error || error ? 'text-sm text-amber-300' : 'text-sm text-zinc-400'}>
        {error ||
          (status.error
            ? t(status.error)
            : status.ready
              ? t('Turn on export for a subscription, in an auto rule, or for selected Library videos.')
              : t('Off. Enter the folder your media server watches.'))}
      </p>
    </section>
  )
}
