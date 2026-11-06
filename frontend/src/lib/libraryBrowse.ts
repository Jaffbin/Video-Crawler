import type { LibrarySort } from './library'

export interface LibraryBrowse {
  query: string
  source: string
  format: string
  kind: string
  favoritesOnly: boolean
  collectionFilter: string
  smartFilter: string
  continuing: boolean
  sort: LibrarySort
  page: number
  pageSize: number
}
export const DEFAULT_BROWSE: LibraryBrowse = {
  query: '',
  source: '',
  format: '',
  kind: '',
  favoritesOnly: false,
  collectionFilter: '',
  smartFilter: '',
  continuing: false,
  sort: 'newest',
  page: 0,
  pageSize: 50,
}
export function browseKey(root: string) {
  return 'grab-library-browse:' + root
}
export function loadBrowse(root: string): LibraryBrowse {
  try {
    const value = JSON.parse(localStorage.getItem(browseKey(root)) || '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { ...DEFAULT_BROWSE }
    const text = (key: string) => (typeof value[key] === 'string' ? value[key].slice(0, 1000) : '')
    return {
      query: text('query'),
      source: text('source'),
      format: text('format'),
      kind: ['video', 'audio', 'image'].includes(value.kind) ? value.kind : '',
      favoritesOnly: value.favoritesOnly === true,
      collectionFilter: text('collectionFilter'),
      smartFilter: text('smartFilter'),
      continuing: value.continuing === true,
      sort: ['newest', 'oldest', 'name', 'largest'].includes(value.sort) ? value.sort : 'newest',
      page: Number.isSafeInteger(value.page) && value.page >= 0 ? value.page : 0,
      pageSize: [25, 50, 100].includes(value.pageSize) ? value.pageSize : 50,
    }
  } catch {
    return { ...DEFAULT_BROWSE }
  }
}
