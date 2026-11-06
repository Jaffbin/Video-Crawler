import { Film, Music } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { fileUrl } from '../../api/client'
import { useI18n } from '../../i18n'
import { fileKind } from '../../lib/library'
import type { FileItem } from '../../types/api'

export function MediaArtwork({ file, onOpen }: { file: FileItem; onOpen: () => void }) {
  const { t } = useI18n()
  const button = useRef<HTMLButtonElement>(null)
  const [visible, setVisible] = useState(false)
  const [failed, setFailed] = useState(false)
  const kind = fileKind(file)
  useEffect(() => {
    setFailed(false)
    if (!button.current || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '100px' },
    )
    observer.observe(button.current)
    return () => observer.disconnect()
  }, [file.path, file.thumbnail])
  return (
    <button
      ref={button}
      className="media-artwork"
      onClick={onOpen}
      aria-label={t('View details for {name}', { name: file.name })}
    >
      {file.thumbnail && !failed ? (
        <img src={fileUrl(file.thumbnail)} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : kind === 'video' && file.complete !== false && visible && !failed ? (
        <video
          src={fileUrl(file.path)}
          preload="metadata"
          muted
          playsInline
          aria-hidden
          onLoadedMetadata={(event) => {
            const media = event.currentTarget
            if (Number.isFinite(media.duration) && media.duration > 0)
              media.currentTime = Math.min(0.1, media.duration / 2)
          }}
          onError={() => setFailed(true)}
        />
      ) : kind === 'audio' ? (
        <Music aria-hidden size={28} />
      ) : (
        <Film aria-hidden size={28} />
      )}
    </button>
  )
}
