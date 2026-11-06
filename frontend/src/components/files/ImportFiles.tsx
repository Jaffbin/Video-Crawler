import { Upload, Loader2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { importLibraryFile } from '../../api/client'
import { useI18n } from '../../i18n'
import type { ToastFn } from '../../hooks/useToasts'
import { formatBytes } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const extensions =
  '.mp4,.webm,.mkv,.mov,.mp3,.m4a,.aac,.alac,.flac,.ogg,.opus,.wav,.aiff,.aif,.wma,.mka,.jpg,.jpeg,.png,.webp,.gif,.avif'
export function ImportFiles({ onRefresh, onToast }: { onRefresh: () => void; onToast: ToastFn }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  function choose(selected: FileList | File[]) {
    if (busy) return
    const selectedFiles = Array.from(selected)
    if (selectedFiles.length > 100) {
      setErrors([t('Choose up to 100 files at a time.')])
      return
    }
    setFiles(selectedFiles)
    setErrors([])
  }

  async function start() {
    const cancel = new AbortController()
    controller.current = cancel
    setBusy(true)
    setErrors([])
    let imported = 0,
      duplicates = 0
    const failed: File[] = [],
      problems: string[] = []
    try {
      for (let index = 0; index < files.length; index++) {
        if (cancel.signal.aborted) {
          failed.push(...files.slice(index))
          break
        }
        const file = files[index]
        if (
          !extensions.split(',').includes('.' + file.name.split('.').pop()?.toLowerCase()) ||
          !file.size ||
          file.size > 8 * 1024 ** 3
        ) {
          failed.push(file)
          problems.push(`${file.name}: ${t('Choose a supported non-empty media file up to 8 GiB.')}`)
          continue
        }
        try {
          const result = await importLibraryFile(file, cancel.signal, (percent) =>
            setProgress(
              t('Importing {name} · {percent}% ({index}/{count})', {
                name: file.name,
                percent,
                index: index + 1,
                count: files.length,
              }),
            ),
          )
          if (result.duplicate) duplicates++
          else imported++
          onRefresh()
        } catch (error) {
          failed.push(file)
          if (cancel.signal.aborted) {
            failed.push(...files.slice(index + 1))
            break
          }
          problems.push(
            `${file.name}: ${t(error instanceof Error ? error.message : 'Could not import this file.')}`,
          )
        }
      }
      setFiles(failed)
      setErrors(problems)
      onToast(
        t('Imported {count} files; skipped {duplicates} duplicates; {failed} remaining.', {
          count: imported,
          duplicates,
          failed: failed.length,
        }),
        problems.length > 0,
      )
      if (cancel.signal.aborted) onToast(t('Import stopped. Completed files remain in Library.'))
    } finally {
      setBusy(false)
      setProgress('')
      controller.current = null
    }
  }
  function close() {
    controller.current?.abort()
    setOpen(false)
  }
  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Upload aria-hidden size={15} />
        {t('Import local files')}
      </Button>
      <Modal open={open} onClose={close} title={t('Import local files')}>
        <div className="grid gap-4">
          <p className="text-sm text-zinc-300">
            {t('Files are copied into the current library. Your original files stay where they are.')}
          </p>
          <label
            className="import-dropzone"
            onDragOver={(event) => {
              event.preventDefault()
              event.stopPropagation()
            }}
            onDrop={(event) => {
              event.preventDefault()
              event.stopPropagation()
              choose(event.dataTransfer.files)
            }}
          >
            <Upload aria-hidden size={24} />
            <span>{t('Choose files or drop them here')}</span>
            <input
              type="file"
              multiple
              accept={extensions}
              disabled={busy}
              aria-label={t('Local media files')}
              onChange={(event) => {
                if (event.target.files) choose(event.target.files)
                event.target.value = ''
              }}
            />
          </label>
          <p className="text-xs text-zinc-400">
            {t(
              'Up to 100 files per batch, 8 GiB per file. Duplicate imports are skipped; existing files are never overwritten.',
            )}
          </p>
          {!!files.length && (
            <p className="text-sm">
              {t('{count} selected', { count: files.length })} ·{' '}
              {formatBytes(files.reduce((size, file) => size + file.size, 0))}
            </p>
          )}
          <ul className="max-h-36 overflow-y-auto text-xs text-zinc-400">
            {files.map((file, index) => (
              <li key={index} className="truncate" title={file.name}>
                {file.name}
              </li>
            ))}
          </ul>
          {busy && (
            <p role="status" className="break-words text-sm">
              {progress || t('Preparing import…')}
            </p>
          )}
          {!!errors.length && (
            <div role="alert" className="grid gap-1 break-words text-sm text-red-300">
              {errors.map((error, index) => (
                <p key={index}>{error}</p>
              ))}
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={busy ? () => controller.current?.abort() : close}>
              {t(busy ? 'Stop import' : 'Close')}
            </Button>
            <Button variant="primary" disabled={busy || !files.length} onClick={start}>
              {busy && <Loader2 aria-hidden size={15} className="animate-spin" />}
              {t('Import selected files')}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  )
}
