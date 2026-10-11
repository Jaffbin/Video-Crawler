import { Button } from '../ui/Button'
import { useI18n } from '../../i18n'

interface Props {
  onOpenSetup?: () => void
  online: boolean
  ffmpeg: boolean
  showYoutubeIssues: boolean
  onOpenDiagnostics: () => void
  onDismissYoutubeIssues: () => void
}

export function Banners({
  onOpenSetup,
  online,
  ffmpeg,
  showYoutubeIssues,
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
      {online && showYoutubeIssues && (
        <div className="flex flex-wrap items-center justify-center gap-3 border-b border-amber-400/10 bg-amber-400/[.06] px-4 py-2 text-sm text-amber-200">
          <span>{t('Some site download features need preparation.')}</span>
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
