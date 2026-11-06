import type { FileItem } from '../types/api'

export type LibrarySort = 'newest' | 'oldest' | 'name' | 'largest'

export function displayFilename(name: string, limit = 24): string {
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const extension = dot > 0 ? name.slice(dot) : ''
  const characters = Array.from(stem)
  return characters.length > limit ? characters.slice(0, limit).join('').trimEnd() + '... ' + extension : name
}

export function fileKind(file: Pick<FileItem, 'kind' | 'name'>): 'video' | 'audio' | 'image' {
  if (file.kind) return file.kind
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  if (['jpg', 'jpeg', 'png', 'webp', 'gif', 'avif'].includes(extension)) return 'image'
  return ['mp3', 'm4a', 'aac', 'alac', 'flac', 'ogg', 'opus', 'wav', 'aiff', 'aif', 'wma', 'mka'].includes(
    extension,
  )
    ? 'audio'
    : 'video'
}

export function filterLibrary(
  files: FileItem[],
  query: string,
  source: string,
  format: string,
  from: string,
  to: string,
  sort: LibrarySort,
  kind = '',
): FileItem[] {
  const text = query.trim().toLocaleLowerCase()
  const start = from ? new Date(`${from}T00:00:00`).getTime() / 1000 : -Infinity
  const end = to ? new Date(`${to}T23:59:59.999`).getTime() / 1000 : Infinity
  return files
    .filter(
      (file) =>
        (!kind || fileKind(file) === kind) &&
        (!text ||
          `${file.path} ${file.title || ''} ${(file.tags || []).join(' ')} ${file.note || ''}`
            .toLocaleLowerCase()
            .includes(text)) &&
        (!source || (file.source || 'unknown') === source) &&
        (!format || file.name.toLowerCase().endsWith(format)) &&
        (file.downloaded ?? file.mtime) >= start &&
        (file.downloaded ?? file.mtime) <= end,
    )
    .sort((a, b) =>
      sort === 'name'
        ? a.name.localeCompare(b.name)
        : sort === 'largest'
          ? b.size - a.size
          : sort === 'oldest'
            ? (a.downloaded ?? a.mtime) - (b.downloaded ?? b.mtime)
            : (b.downloaded ?? b.mtime) - (a.downloaded ?? a.mtime),
    )
}
