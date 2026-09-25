import { Film, FolderOpen, Music, Play, RefreshCw, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { fileUrl, openFile, openFolder } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { formatBytes, formatDate } from '../../lib/utils'
import type { FileItem } from '../../types/api'
import { Button } from '../ui/Button'

const AUDIO = new Set(['.mp3', '.m4a', '.aac', '.flac', '.ogg', '.opus'])

interface Props {
  files: FileItem[]
  windowMode: boolean
  onRefresh: () => void
  onToast: ToastFn
}

export function FileGallery({ files, windowMode, onRefresh, onToast }: Props) {
  const [query, setQuery] = useState('')
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? files.filter((f) => f.path.toLowerCase().includes(q)) : files
  }, [files, query])
  const report = (e: unknown) => onToast(e instanceof Error ? e.message : 'Could not open it', true)
  const isAudio = (name: string) => AUDIO.has(name.slice(name.lastIndexOf('.')).toLowerCase())

  return (
    <section className="card grid content-start gap-4" aria-labelledby="files-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="eyebrow">Library</div>
          <h2 id="files-title" className="mt-1 text-lg font-semibold">
            Downloaded files
          </h2>
        </div>
        <Button variant="ghost" onClick={onRefresh}>
          <RefreshCw aria-hidden size={15} /> Refresh
        </Button>
      </div>

      <label className="relative">
        <span className="sr-only">Search files</span>
        <Search
          aria-hidden
          size={15}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
        />
        <input
          className="field !pl-9"
          type="search"
          placeholder="Search files"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      {files.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          No completed files yet.
        </p>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          No files match your search.
        </p>
      ) : (
        <ul className="grid gap-1">
          {shown.map((f) => (
            <li key={f.path} className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-white/[.03]">
              <span
                aria-hidden
                className="grid size-8 shrink-0 place-items-center rounded-lg bg-white/[.05] text-zinc-400"
              >
                {isAudio(f.name) ? <Music size={15} /> : <Film size={15} />}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm" title={f.path}>
                {f.path}
              </span>
              <span className="hidden shrink-0 text-xs tabular-nums text-zinc-500 sm:inline">
                {formatBytes(f.size)}
              </span>
              <span className="hidden shrink-0 text-xs text-zinc-500 md:inline">{formatDate(f.mtime)}</span>
              {windowMode ? (
                <button type="button" className="action-btn" onClick={() => openFile(f.path).catch(report)}>
                  <Play aria-hidden size={13} /> Open
                </button>
              ) : (
                <a className="action-btn" href={fileUrl(f.path)} target="_blank" rel="noreferrer">
                  <Play aria-hidden size={13} /> Play
                </a>
              )}
              <a className="action-btn" href={fileUrl(f.path)} download={f.name}>
                 Download
              </a>



              <button
                type="button"
                className="action-btn"
                onClick={() => openFolder(f.path).catch(report)}
                aria-label={`Show ${f.name} in folder`}
              >
                <FolderOpen aria-hidden size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
