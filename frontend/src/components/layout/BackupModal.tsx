import { useRef, useState } from 'react'
import { exportBackup, previewBackup, restoreBackup } from '../../api/client'
import { applyBrowserPreferences, browserPreferences, type BackupReview } from '../../lib/backup'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

export function BackupModal({
  open,
  onClose,
  onRestored,
}: {
  open: boolean
  onClose: () => void
  onRestored: () => void
}) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [backup, setBackup] = useState<unknown>(null)
  const [review, setReview] = useState<BackupReview | null>(null)
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('')
  async function exportFile() {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const data = await exportBackup(browserPreferences(true))
      const url = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `video-grabber-backup-${new Date().toISOString().slice(0, 10)}.json`
      document.body.append(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
      setMessage(t('Backup file prepared. Keep it with a separate copy of your media.'))
    } catch (cause) {
      setError(t(cause instanceof Error ? cause.message : 'Could not create backup.'))
    } finally {
      setBusy(false)
    }
  }
  async function readFile(file: File | undefined) {
    if (!file) return
    setReview(null)
    setBackup(null)
    setError('')
    setMessage('')
    setBusy(true)
    try {
      if (file.size > 16 * 1024 ** 2) throw new Error('Choose a backup file smaller than 16 MiB.')
      let value: unknown
      try {
        value = JSON.parse(await file.text())
      } catch {
        throw new Error('Choose a valid JSON backup file.')
      }
      const next = await previewBackup(value, browserPreferences())
      setBackup(value)
      setReview(next)
    } catch (cause) {
      setError(t(cause instanceof Error ? cause.message : 'Could not preview backup.'))
    } finally {
      setBusy(false)
    }
  }
  async function restore() {
    if (!review) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await restoreBackup(backup, browserPreferences(), review.review_token)
      try {
        applyBrowserPreferences(result.browser)
      } catch {
        throw new Error(
          'Library data was restored, but browser settings could not be saved. Preview again to retry.',
        )
      }
      setReview(null)
      setBackup(null)
      onRestored()
      setMessage(t('Restore finished. Existing values and media files were kept.'))
    } catch (cause) {
      setError(t(cause instanceof Error ? cause.message : 'Could not restore backup.'))
      // A retry always previews fresh state, including after a possibly delivered request.
      setReview(null)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal
      open={open}
      title={t('Backup and restore')}
      onClose={() => {
        if (!busy) onClose()
      }}
    >
      <div className="grid gap-4 text-sm">
        <p>
          {t(
            'Back up preferences, custom presets, favorites, collections, tags, notes and playback progress.',
          )}
        </p>
        <p className="text-xs text-zinc-400">
          {t(
            'Media files, queues, subscriptions, sign-in data and proxy information are excluded. Save media separately with the same folder structure.',
          )}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => void exportFile()}>
            {t('Export backup')}
          </Button>
          <Button disabled={busy} onClick={() => input.current?.click()}>
            {t('Choose backup to preview')}
          </Button>
          <input
            ref={input}
            hidden
            type="file"
            accept=".json,application/json"
            aria-label={t('Backup JSON file')}
            onChange={(event) => {
              void readFile(event.target.files?.[0])
              event.target.value = ''
            }}
          />
          {!!backup && !review && (
            <Button
              disabled={busy}
              onClick={() => {
                setBusy(true)
                setError('')
                void previewBackup(backup, browserPreferences())
                  .then(setReview)
                  .catch((cause) => setError(t(String(cause.message))))
                  .finally(() => setBusy(false))
              }}
            >
              {t('Preview again')}
            </Button>
          )}
        </div>
        {busy && <p role="status">{t('Working…')}</p>}
        {error && (
          <p role="alert" className="text-red-300">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="text-emerald-300">
            {message}
          </p>
        )}
        {review && (
          <section
            className="grid gap-3 rounded-xl border border-white/[.1] p-3"
            aria-label={t('Restore preview')}
          >
            <h3 className="font-semibold">{t('Restore preview')}</h3>
            <p>
              {t(
                'Will add or merge: {files} media records, {collections} collections, {presets} presets and {settings} settings.',
                review.counts,
              )}
            </p>
            {!!review.counts.smart_collections && (
              <p>
                {t('{count} smart collections will be added.', { count: review.counts.smart_collections })}
              </p>
            )}
            <p>
              {t('{count} conflicting values will keep the current value.', {
                count: review.counts.conflicts,
              })}
            </p>
            <p className="text-xs text-zinc-400">
              {t(
                'Tags and collection membership are combined. Existing notes, favorites, progress and saved settings win conflicts. Files match by relative path and size; content is not verified.',
              )}
            </p>
            {!!review.skipped.length && (
              <div>
                <p>
                  {t('{count} unmatched files will be skipped. Copy the media first, then import again.', {
                    count: review.skipped.length,
                  })}
                </p>
                <ul className="mt-2 max-h-40 overflow-auto text-xs text-zinc-400">
                  {review.skipped.map((item) => (
                    <li key={item.path} className="break-all py-1">
                      {item.path} · {t(item.reason === 'size' ? 'File size differs' : 'File not found')}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <Button variant="primary" disabled={busy} onClick={() => void restore()}>
              {t('Restore missing data and merge')}
            </Button>
          </section>
        )}
      </div>
    </Modal>
  )
}
