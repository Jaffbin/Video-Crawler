import { useEffect, useRef, useState } from 'react'
import { extractUrls, looksLikeTextFile } from '../lib/urls'

const MAX_FILE_BYTES = 2_000_000

interface Handlers {
  /** Called with the links found, and a short description of where they came from. */
  onUrls: (urls: string[], source: string) => void
  onProblem: (message: string) => void
}

const isEditable = (el: EventTarget | null) => {
  const node = el as HTMLElement | null
  return !!node && (['INPUT', 'TEXTAREA', 'SELECT'].includes(node.tagName) || node.isContentEditable)
}

/**
 * Paste anywhere on the page, or drop links / text files onto the window.
 * Pasting inside a text field is left alone, the field handles it itself.
 */
export function useUrlImport({ onUrls, onProblem }: Handlers) {
  const [dragging, setDragging] = useState(false)
  const handlers = useRef({ onUrls, onProblem })
  handlers.current = { onUrls, onProblem }

  useEffect(() => {
    let depth = 0
    const hasPayload = (e: DragEvent) =>
      !!e.dataTransfer &&
      [...e.dataTransfer.types].some((t) => ['Files', 'text/uri-list', 'text/plain'].includes(t))

    const onPaste = (e: ClipboardEvent) => {
      if (isEditable(e.target)) return
      const urls = extractUrls(e.clipboardData?.getData('text') ?? '')
      if (urls.length) {
        e.preventDefault()
        handlers.current.onUrls(urls, 'from the clipboard')
      }
    }
    const onEnter = (e: DragEvent) => {
      if (!hasPayload(e)) return
      e.preventDefault()
      depth++
      setDragging(true)
    }
    const onOver = (e: DragEvent) => {
      if (hasPayload(e)) e.preventDefault()
    }
    const onLeave = (e: DragEvent) => {
      if (!hasPayload(e)) return
      depth = Math.max(0, depth - 1)
      if (!depth) setDragging(false)
    }
    const onDrop = async (e: DragEvent) => {
      if (!hasPayload(e)) return
      e.preventDefault()
      depth = 0
      setDragging(false)
      const dt = e.dataTransfer!
      const urls: string[] = []
      for (const file of [...dt.files].slice(0, 20)) {
        if (!looksLikeTextFile(file)) {
          handlers.current.onProblem(`${file.name} is not a text file, skipped`)
        } else if (file.size > MAX_FILE_BYTES) {
          handlers.current.onProblem(`${file.name} is too large, skipped`)
        } else {
          urls.push(...extractUrls(await file.text()))
        }
      }
      if (!dt.files.length)
        urls.push(...extractUrls(`${dt.getData('text/uri-list')}\n${dt.getData('text/plain')}`))
      if (dt.files.length || urls.length) {
        handlers.current.onUrls(
          [...new Set(urls)],
          dt.files.length ? 'from dropped files' : 'from a dropped link',
        )
      }
    }

    document.addEventListener('paste', onPaste)
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragover', onOver)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('drop', onDrop)
    return () => {
      document.removeEventListener('paste', onPaste)
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('drop', onDrop)
    }
  }, [])

  return { dragging }
}
