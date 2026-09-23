import type { DoctorCheck } from '../../types/api'
import { Button } from '../ui/Button'

interface Props {
  online: boolean
  ffmpeg: boolean
  youtubeIssues: DoctorCheck[]
  showYoutubeIssues: boolean
  onOpenDiagnostics: () => void
  onDismissYoutubeIssues: () => void
}

export function Banners({
  online,
  ffmpeg,
  youtubeIssues,
  showYoutubeIssues,
  onOpenDiagnostics,
  onDismissYoutubeIssues,
}: Props) {
  return (
    <>
      {!online && (
        <div
          role="alert"
          className="border-b border-red-400/15 bg-red-500/[.08] px-4 py-2 text-center text-sm text-red-200"
        >
          Connection to the local service was lost. Retrying automatically…
        </div>
      )}
      {online && !ffmpeg && (
        <div className="border-b border-amber-400/10 bg-amber-400/[.06] px-4 py-2 text-center text-sm text-amber-200">
          ffmpeg is not detected. MP4 merging and MP3 conversion will fail.
        </div>
      )}
      {online && showYoutubeIssues && (
        <div className="flex flex-wrap items-center justify-center gap-3 border-b border-amber-400/10 bg-amber-400/[.06] px-4 py-2 text-sm text-amber-200">
          <span>
            YouTube setup incomplete: {youtubeIssues.map((c) => c.label).join(' and ')} not detected. Some
            YouTube formats may be unavailable.
          </span>
          <Button variant="ghost" className="!py-1" onClick={onOpenDiagnostics}>
            Open Diagnostics
          </Button>
          <Button variant="ghost" className="!py-1" onClick={onDismissYoutubeIssues}>
            Dismiss
          </Button>
        </div>
      )}
    </>
  )
}
