import { fileUrl, openFile, type ExistingDownload } from '../../api/client'
import { useI18n } from '../../i18n'
import { showDesktopMain } from '../../lib/desktop'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

export function ExistingDownloads({
  items,
  busy,
  onClose,
  onChoose,
  onError,
  error,
}: {
  items: ExistingDownload[]
  busy: boolean
  onClose: () => void
  onChoose: (action: 'skip' | 'download') => void
  onError: (message: string) => void
  error?: string
}) {
  const { t } = useI18n()
  const different = items.some((item) => item.profile_known && item.settings_match === false)
  return (
    <Modal
      open={items.length > 0}
      title={t('Already downloaded')}
      onClose={() => {
        if (!busy) onClose()
      }}
    >
      <div className="grid gap-4 text-sm">
        {error && (
          <p role="alert" className="text-red-300">
            {error}
          </p>
        )}
        <p>{t('These links have saved files. No new tasks have been added yet.')}</p>
        {different && (
          <p className="text-amber-300">
            {t('Saved settings differ. Another copy will use your current settings.')}
          </p>
        )}
        {items.some((item) => !item.profile_known) && (
          <p className="text-amber-300">
            {t('Some older files have no saved quality settings. Check them before choosing.')}
          </p>
        )}
        <ul className="grid max-h-56 gap-3 overflow-auto">
          {items.map((item) => (
            <li key={item.url + item.path} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 basis-48 break-words">
                {item.name}
                {(item.profile?.quality || item.profile?.abr) && (
                  <small className="block text-zinc-400">
                    {t('Saved quality setting')}:{' '}
                    {item.profile.quality
                      ? item.profile.quality === 'best'
                        ? t('Best available')
                        : t('Up to {quality}p', { quality: item.profile.quality })
                      : item.profile.abr + ' kbps'}
                  </small>
                )}
              </span>
              {window.pywebview ? (
                <Button
                  disabled={busy}
                  onClick={() => void openFile(item.path).catch((error) => onError(String(error)))}
                >
                  {t('Open')}
                </Button>
              ) : (
                <a className="action-btn" target="_blank" rel="noreferrer" href={fileUrl(item.path)}>
                  {t('Open')}
                </a>
              )}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={busy}
            variant={different ? 'default' : 'primary'}
            onClick={() => onChoose('skip')}
          >
            {t('Use existing files')}
          </Button>
          <Button
            disabled={busy}
            variant={different ? 'primary' : 'default'}
            onClick={() => onChoose('download')}
          >
            {t('Download another copy')}
          </Button>
          <Button
            disabled={busy}
            onClick={() => {
              onClose()
              void showDesktopMain('library').catch((error) => onError(String(error)))
            }}
          >
            {t('Open Library')}
          </Button>
          <Button disabled={busy} variant="ghost" onClick={onClose}>
            {t('Cancel')}
          </Button>
        </div>
        <p className="text-xs text-zinc-400">
          {t('Existing files stay unchanged. Other new links will still be added.')}
        </p>
      </div>
    </Modal>
  )
}
