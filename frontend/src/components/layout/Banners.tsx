import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'

interface Props {
  onOpenSetup?: () => void
  online: boolean
  ffmpeg: boolean
  showYoutubeIssues: boolean
  /** Ids of the failed YouTube checks, so the banner can name what is missing. */
  youtubeIssueIds?: string[]
  /** A newer yt-dlp than the one installed, or null when nothing is waiting. */
  updateVersion?: string | null
  updateNeedsRestart?: boolean
  onUpdate?: () => void
  onDismissUpdate?: () => void
  onOpenDiagnostics: () => void
  onDismissYoutubeIssues: () => void
}

export function Banners({
  onOpenSetup,
  online,
  ffmpeg,
  showYoutubeIssues,
  youtubeIssueIds = [],
  updateVersion,
  updateNeedsRestart,
  onUpdate,
  onDismissUpdate,
  onOpenDiagnostics,
  onDismissYoutubeIssues,
}: Props) {
  const { t } = useI18n()
  return (
    <>
      {!online && (
        <div
          role="alert"
          className="border-b border-red-400/15 bg-red-500/[.08] px-4 py-2 text-center text-sm text-red-200"
        >
          {t('Connection to the local service was lost. Retrying automatically…')}
        </div>
      )}
      {online && !ffmpeg && (
        <div className="border-b border-amber-400/10 bg-amber-400/[.06] px-4 py-2 text-center text-sm text-amber-200">
          <span>{t('Video and audio download features need preparation.')}</span>{' '}
          <Button variant="ghost" onClick={onOpenSetup || onOpenDiagnostics}>
            {t('Prepare download features')}
          </Button>
        </div>
      )}
      {online && onUpdate && (updateVersion || updateNeedsRestart) && (
        <div className="flex flex-wrap items-center justify-center gap-3 border-b border-sky-400/10 bg-sky-400/[.06] px-4 py-2 text-sm text-sky-200">
          <span>
            {updateVersion
              ? t(
                  'yt-dlp {version} is available. Sites change often, and updating fixes many download errors.',
                  { version: updateVersion },
                )
              : t('yt-dlp was updated. Restart the app to use it.')}
          </span>
          <Button variant="ghost" className="!py-1" onClick={onUpdate}>
            {updateVersion ? t('Update now') : t('Open updates')}
          </Button>
          {updateVersion && onDismissUpdate && (
            <Button variant="ghost" className="!py-1" onClick={onDismissUpdate}>
              {t('Dismiss')}
            </Button>
          )}
        </div>
      )}
      {online && showYoutubeIssues && (
        <div className="flex flex-wrap items-center justify-center gap-3 border-b border-amber-400/10 bg-amber-400/[.06] px-4 py-2 text-sm text-amber-200">
          <span>
            {youtubeIssueIds.includes('js_runtime')
              ? t('YouTube downloads need the Deno helper to find every format.')
              : youtubeIssueIds.includes('ejs')
                ? t('YouTube downloads need one more yt-dlp component.')
                : t('Some site download features need preparation.')}
          </span>
          <Button variant="ghost" className="!py-1" onClick={onOpenSetup || onOpenDiagnostics}>
            {t('Prepare download features')}
          </Button>
          <Button variant="ghost" className="!py-1" onClick={onDismissYoutubeIssues}>
            {t('Dismiss')}
          </Button>
        </div>
      )}
    </>
  )
}
