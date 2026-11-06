import {
  Ellipsis,
  Download,
  ExternalLink,
  FolderOpen,
  Image as ImageIcon,
  Pencil,
  Play,
  RefreshCw,
  Search,
  SlidersHorizontal,
  LayoutGrid,
  List,
  Star,
  ListPlus,
  Trash2,
} from 'lucide-react'
import { useEffect, useId, useMemo, useState, type SetStateAction } from 'react'
import {
  batchLibrary,
  repairFile,
  fileUrl,
  getRecoveryFiles,
  openFile,
  openFolder,
  openExternalUrl,
  renameFile,
  restoreFile,
  purgeFile,
  trashFile,
  organizeFiles,
} from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { formatBytes, formatDate, formatDuration } from '../../lib/utils'
import type { FileItem, RecoveryFile, LibraryScan, LibraryCollection, SmartCollection } from '../../types/api'
import { BUILTIN_SMART_COLLECTIONS, matchesSmartCollection, smartName } from '../../lib/smartCollections'
import { CollectionManager } from './CollectionManager'
import { ImportFiles } from './ImportFiles'
import { MediaArtwork } from './MediaArtwork'
import { MediaDetails } from './MediaDetails'
import { LibraryFilters } from './LibraryFilters'
import { LibraryOrganizer } from './LibraryOrganizer'
import { displayFilename, fileKind, filterLibrary, type LibrarySort } from '../../lib/library'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Popover } from '../ui/Popover'
import { SelectionScope } from '../ui/SelectionScope'
import { browseKey, loadBrowse, DEFAULT_BROWSE } from '../../lib/libraryBrowse'
import { useI18n } from '../../i18n'
import { AUDIO_QUEUE_LIMIT, playableAudio, type AudioPlayerController } from '../../lib/audioPlayer'

function ImageThumbnail({ file, onPreview }: { file: FileItem; onPreview: () => void }) {
  const { t } = useI18n()
  const [failed, setFailed] = useState(false)
  return (
    <button
      className="grid size-12 shrink-0 place-items-center overflow-hidden rounded-lg bg-white/5"
      aria-label={t('Preview {name}', { name: file.name })}
      onClick={onPreview}
    >
      {failed ? (
        <ImageIcon aria-hidden size={18} />
      ) : (
        <img
          src={fileUrl(file.path)}
          alt=""
          loading="lazy"
          decoding="async"
          className="size-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </button>
  )
}

interface Props {
  audioPlayer?: AudioPlayerController
  root?: string
  files: FileItem[]
  windowMode: boolean
  onRefresh: () => void
  onToast: ToastFn
  editingBlocked?: boolean
  onNewDownload?: () => void
  scan?: LibraryScan
  collections?: LibraryCollection[]
  smartCollections?: SmartCollection[]
}

export function FileGallery({
  audioPlayer,
  root = '',
  files,
  windowMode,
  onRefresh,
  onToast,
  editingBlocked = false,
  onNewDownload,
  scan,
  collections = [],
  smartCollections = [],
}: Props) {
  const { t } = useI18n()
  const [selected, setSelected] = useState<string[]>([])
  const [recoverySelected, setRecoverySelected] = useState<string[]>([])
  const selectedKeys = useMemo(() => new Set(selected), [selected])
  const recoveryKeys = useMemo(() => new Set(recoverySelected), [recoverySelected])
  const [batchAction, setBatchAction] = useState<'trash' | 'purge' | null>(null)
  const [browse, setBrowse] = useState(() => loadBrowse(root))
  const {
    query,
    source,
    format,
    kind,
    favoritesOnly,
    collectionFilter,
    smartFilter,
    continuing,
    sort,
    page,
    pageSize,
  } = browse
  const smartChoices = useMemo(() => [...BUILTIN_SMART_COLLECTIONS, ...smartCollections], [smartCollections])
  const activeSmart = smartChoices.find((item) => item.id === smartFilter)
  const [smartNow, setSmartNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    setSmartNow(Date.now() / 1000)
    if (!activeSmart?.rules.recent_days) return
    const timer = window.setInterval(() => setSmartNow(Date.now() / 1000), 60000)
    return () => window.clearInterval(timer)
  }, [smartFilter, activeSmart?.rules.recent_days])
  const setQuery = (query: string) => setBrowse((value) => ({ ...value, query }))
  const setSource = (source: string) => setBrowse((value) => ({ ...value, source }))
  const setFormat = (format: string) => setBrowse((value) => ({ ...value, format }))
  const setKind = (kind: string) => setBrowse((value) => ({ ...value, kind }))
  const setFavoritesOnly = (favoritesOnly: boolean) => setBrowse((value) => ({ ...value, favoritesOnly }))
  const setCollectionFilter = (collectionFilter: string) =>
    setBrowse((value) => ({ ...value, collectionFilter }))
  const setSmartFilter = (smartFilter: string) => setBrowse((value) => ({ ...value, smartFilter }))
  const setContinuing = (continuing: boolean) => setBrowse((value) => ({ ...value, continuing }))
  const setSort = (sort: LibrarySort) => setBrowse((value) => ({ ...value, sort }))
  const setPage = (page: SetStateAction<number>) =>
    setBrowse((value) => ({ ...value, page: typeof page === 'function' ? page(value.page) : page }))
  const setPageSize = (pageSize: number) => setBrowse((value) => ({ ...value, pageSize }))
  useEffect(() => {
    try {
      localStorage.setItem(browseKey(root), JSON.stringify(browse))
    } catch {
      /* Browsing works without storage. */
    }
  }, [root, browse])
  const [organizing, setOrganizing] = useState<string[] | null>(null)
  const [popup, setPopup] = useState<{ kind: 'filters' | 'file'; anchor: HTMLElement; path?: string } | null>(
    null,
  )
  const popoverId = useId()
  const [details, setDetails] = useState<{ file: FileItem; autoPlay: boolean } | null>(null)
  const [layout, setLayout] = useState<'grid' | 'list'>(() => {
    try {
      return localStorage.getItem('grab-library-layout') === 'list' ? 'list' : 'grid'
    } catch {
      return 'grid'
    }
  })
  function chooseLayout(next: 'grid' | 'list') {
    setLayout(next)
    try {
      localStorage.setItem('grab-library-layout', next)
    } catch {
      /* storage may be disabled */
    }
  }
  const [editing, setEditing] = useState<{ kind: 'rename' | 'trash'; file: FileItem } | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [recoveryOpen, setRecoveryOpen] = useState(false)
  const [deleting, setDeleting] = useState<RecoveryFile | null>(null)
  const [recovery, setRecovery] = useState<RecoveryFile[]>([])
  const [picture, setPicture] = useState<FileItem | null>(null)
  const [originalSize, setOriginalSize] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const [dimensions, setDimensions] = useState('')
  useEffect(() => {
    if (collectionFilter && !collections.some((collection) => collection.id === collectionFilter)) {
      setCollectionFilter('')
      setPage(0)
    }
  }, [collections, collectionFilter])
  useEffect(() => {
    if (smartFilter && !smartChoices.some((collection) => collection.id === smartFilter)) {
      setSmartFilter('')
      setPage(0)
    }
  }, [smartChoices, smartFilter])
  const shown = useMemo(() => {
    // New file snapshots must use the current time, not the previous minute's timer tick.
    const now = Date.now() / 1000
    return filterLibrary(files, query, source, format, '', '', sort, kind).filter(
      (file) =>
        (!favoritesOnly || file.favorite) &&
        (!continuing || matchesSmartCollection(file, { playback: 'in_progress' })) &&
        (!collectionFilter || file.collections?.includes(collectionFilter)) &&
        (!activeSmart || matchesSmartCollection(file, activeSmart.rules, now)),
    )
  }, [
    files,
    query,
    source,
    format,
    sort,
    kind,
    favoritesOnly,
    collectionFilter,
    continuing,
    activeSmart,
    smartNow,
  ])
  const currentPage = Math.min(page, Math.max(0, Math.ceil(shown.length / pageSize) - 1))
  const visible = shown.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
  const shownAudio = useMemo(() => shown.filter(playableAudio), [shown])
  const activeFilters = [kind, source, format, collectionFilter, smartFilter, sort !== 'newest'].filter(
    Boolean,
  ).length
  const filterSummary = [
    kind && [t('Media type'), t({ video: 'Videos', audio: 'Audio', image: 'Images' }[kind] || kind)],
    source && [
      t('Source site'),
      source === 'unknown' ? t('Unknown source') : source === 'local' ? t('Local file') : source,
    ],
    format && [t('Format'), format.slice(1).toUpperCase()],
    collectionFilter && [t('Collection'), collections.find((item) => item.id === collectionFilter)?.name],
    activeSmart && [t('Smart collection'), smartName(activeSmart, t)],
    sort !== 'newest' && [
      t('Sort files'),
      t({ oldest: 'Oldest first', name: 'Name', largest: 'Largest first' }[sort]),
    ],
  ].filter((item): item is string[] => Array.isArray(item) && typeof item[1] === 'string')
  const hasFilters = !!(query || favoritesOnly || continuing || activeFilters)
  function resetFilters() {
    setQuery('')
    setSource('')
    setFormat('')
    setKind('')
    setCollectionFilter('')
    setSmartFilter('')
    setSort('newest')
    setFavoritesOnly(false)
    setContinuing(false)
    setPage(0)
  }
  useEffect(() => {
    if (popup?.kind === 'file' && !visible.some((file) => file.path === popup.path)) setPopup(null)
  }, [popup, visible])
  const chosen = useMemo(() => files.filter((file) => selectedKeys.has(file.path)), [files, selectedKeys])
  const recoveryChosen = useMemo(
    () => recovery.filter((file) => recoveryKeys.has(file.id)),
    [recovery, recoveryKeys],
  )
  async function organize(
    paths: string[],
    patch: { favorite?: boolean; collection_id?: string; remove?: boolean },
  ) {
    setBusy(true)
    setError('')
    const failed: string[] = []
    let changed = 0
    try {
      for (let offset = 0; offset < paths.length; offset += 200) {
        const result = await organizeFiles(paths.slice(offset, offset + 200), patch)
        changed += result.processed.length
        failed.push(...result.failed.map((item) => item.item))
      }
      if (failed.length) {
        setError(t('Some files could not be changed. Refresh Library and try again.'))
        setSelected(failed)
      }
      onToast(
        t('Updated {count} files; {failed} could not be changed.', { count: changed, failed: failed.length }),
        failed.length > 0,
      )
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
      report(e)
    } finally {
      if (changed) onRefresh()
      setBusy(false)
    }
  }
  function toggle(value: string, recoveryMode = false) {
    const setter = recoveryMode ? setRecoverySelected : setSelected
    setter((items) => (items.includes(value) ? items.filter((item) => item !== value) : [...items, value]))
  }
  function selectPage() {
    const paths = visible.map((file) => file.path)
    setSelected((items) => [...new Set([...items, ...paths])])
  }
  async function changeMany(action: 'trash' | 'restore' | 'purge') {
    const items = action === 'trash' ? chosen.map((file) => file.path) : recoveryChosen.map((file) => file.id)
    setBusy(true)
    setError('')
    try {
      const result: { processed: string[]; failed: Array<{ item: string; error: string }> } = {
        processed: [],
        failed: [],
      }
      const recoveryIds: string[] = []
      for (let offset = 0; offset < items.length; offset += 200) {
        try {
          const chunk = await batchLibrary(items.slice(offset, offset + 200), action)
          result.processed.push(...chunk.processed)
          result.failed.push(...chunk.failed)
          recoveryIds.push(...(chunk.recovery_ids || []))
        } catch (e) {
          result.failed.push(
            ...items
              .slice(offset)
              .map((item) => ({ item, error: e instanceof Error ? e.message : 'That did not work' })),
          )
          break
        }
      }
      const setter = action === 'trash' ? setSelected : setRecoverySelected
      const processed = new Set(result.processed)
      setter((values) => values.filter((value) => !processed.has(value)))
      if (action !== 'trash') setRecovery((values) => values.filter((value) => !processed.has(value.id)))
      onToast(
        t('Updated {count} files; {failed} could not be changed.', {
          count: result.processed.length,
          failed: result.failed.length,
        }),
        result.failed.length > 0,
        recoveryIds.length ? undoAction(recoveryIds) : undefined,
      )
      if (result.failed.length) {
        const reasons = result.failed.slice(0, 5).map((failure) => {
          const path = recovery.find((file) => file.id === failure.item)?.path || failure.item
          const message = failure.error.includes('already exists')
            ? 'A file with this name already exists. Rename it before restoring.'
            : /not found|no longer exists/.test(failure.error)
              ? 'This file is no longer available. Refresh the list.'
              : failure.error.includes('Invalid recovery record')
                ? 'This item’s recovery information is damaged.'
                : 'Close any player using this file and try again. Check available disk space if it still fails.'
          return displayFilename(path.split(/[\\/]/).pop() || path) + ': ' + t(message)
        })
        setError(
          t('Some files could not be changed. They remain selected so you can try again.') +
            ' ' +
            reasons.join(' '),
        )
      } else setBatchAction(null)
      if (result.processed.length) onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  async function requestRepair(file: FileItem) {
    setBusy(true)
    try {
      await repairFile(file.path)
      onToast(t('Repair added to Queue. Your original files are kept until it succeeds.'))
      onRefresh()
    } catch (e) {
      report(e)
    } finally {
      setBusy(false)
    }
  }
  const sources = useMemo(() => [...new Set(files.map((file) => file.source || 'unknown'))].sort(), [files])
  const formats = useMemo(
    () => [...new Set(files.map((file) => '.' + file.name.split('.').pop()?.toLowerCase()))].sort(),
    [files],
  )
  const report = (e: unknown) => onToast(t(e instanceof Error ? e.message : 'Could not open it'), true)
  function addAudio(items: FileItem[]) {
    if (!audioPlayer) return
    const added = audioPlayer.enqueue(items)
    onToast(
      t('Added {count} tracks to playback queue. Existing tracks are kept once; the limit is 500.', {
        count: added,
      }),
    )
  }
  function undoAction(ids: string[]) {
    let pending = [...ids]
    return {
      label: 'Undo',
      onClick: async () => {
        while (pending.length) {
          const chunk = pending.slice(0, 200)
          const result = await batchLibrary(chunk, 'restore')
          const before = pending.length
          pending = pending.filter((id) => !result.processed.includes(id))
          if (result.processed.length) onRefresh()
          if (result.failed.length || pending.length === before)
            throw new Error(
              'Could not undo. A file may already exist or be in use. Try again or open Recovery.',
            )
        }
        onToast(t('Files restored'))
      },
    }
  }
  function previewImage(file: FileItem) {
    setPicture(file)
    setOriginalSize(false)
    setImageFailed(false)
    setDimensions('')
  }

  async function editFile() {
    if (!editing) return
    setBusy(true)
    setError('')
    try {
      if (editing.kind === 'rename') {
        const renamed = await renameFile(editing.file.path, name)
        audioPlayer?.rename(editing.file.path, renamed.path)
        onToast(t('File renamed'))
      } else {
        const result = await trashFile(editing.file.path)
        onToast(t('File moved to recovery.'), false, undoAction([result.id]))
      }
      setEditing(null)
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function openRecovery() {
    setRecoveryOpen(true)
    setRecoverySelected([])
    setBatchAction(null)
    setDeleting(null)
    setBusy(true)
    setError('')
    try {
      setRecovery((await getRecoveryFiles()).items)
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function removeRecovery() {
    if (!deleting) return
    setBusy(true)
    setError('')
    try {
      await purgeFile(deleting.id)
      setRecovery((items) => items.filter((item) => item.id !== deleting.id))
      setDeleting(null)
      onToast(t('File permanently deleted'))
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  async function restore(id: string) {
    setBusy(true)
    setError('')
    try {
      await restoreFile(id)
      setRecovery((items) => items.filter((item) => item.id !== id))
      onToast(t('File restored'))
      onRefresh()
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card library-panel grid content-start gap-4" aria-labelledby="files-title">
      <div className="panel-toolbar library-toolbar">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="eyebrow library-eyebrow">{t('Library')}</div>
            <h2 id="files-title" className="mt-1 text-lg font-semibold">
              {t('Downloaded files')}
            </h2>
          </div>
          <div className="compact-actions library-tools flex flex-wrap gap-2">
            <ImportFiles onRefresh={onRefresh} onToast={onToast} />
            <CollectionManager
              collections={collections}
              files={files}
              smartCollections={smartCollections}
              onRefresh={onRefresh}
              onToast={onToast}
              onViewSmart={(id) => {
                resetFilters()
                setSmartFilter(id)
              }}
            />
            <Button variant="ghost" disabled={busy} onClick={openRecovery}>
              {t('Recovery')}
            </Button>
            <LibraryOrganizer
              root={root}
              editingBlocked={editingBlocked || busy}
              onRecycled={(result) => {
                onToast(
                  t('Updated {count} files; {failed} could not be changed.', {
                    count: result.processed.length,
                    failed: result.failed.length,
                  }),
                  result.failed.length > 0,
                  result.recovery_ids.length ? undoAction(result.recovery_ids) : undefined,
                )
                if (result.processed.length) onRefresh()
              }}
            />
            <Button variant="ghost" onClick={onRefresh}>
              <RefreshCw aria-hidden size={15} /> {t('Refresh')}
            </Button>
          </div>
        </div>

        <label className="library-search relative">
          <span className="sr-only">{t('Search files')}</span>
          <Search
            aria-hidden
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          />
          <input
            className="field !pl-9"
            type="search"
            placeholder={t('Search titles, tags and notes')}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPage(0)
            }}
          />
        </label>
      </div>
      <div className="library-controls flex flex-wrap items-center gap-3">
        <Button
          aria-label={t('Continue watching / listening')}
          aria-pressed={continuing}
          onClick={() => {
            setContinuing(!continuing)
            setPage(0)
          }}
        >
          <span className="library-continue-full">{t('Continue watching / listening')}</span>
          <span className="library-continue-short" aria-hidden>
            {t('Resume playback')}
          </span>
        </Button>
        <Button
          aria-pressed={favoritesOnly}
          onClick={() => {
            setFavoritesOnly(!favoritesOnly)
            setPage(0)
          }}
        >
          <Star aria-hidden size={15} className={favoritesOnly ? 'fill-amber-300 text-amber-300' : ''} />{' '}
          {t('Favorites')}
        </Button>
        <Button
          aria-label={t('Filters')}
          aria-haspopup="dialog"
          aria-expanded={popup?.kind === 'filters'}
          aria-controls={popup?.kind === 'filters' ? popoverId : undefined}
          title={activeFilters ? t('{count} active filters', { count: activeFilters }) : t('Filters')}
          onClick={(event) => {
            const anchor = event.currentTarget
            setPopup((current) => (current?.kind === 'filters' ? null : { kind: 'filters', anchor }))
          }}
        >
          <SlidersHorizontal aria-hidden size={15} /> {t('Filters')}
          {activeFilters > 0 && (
            <span aria-hidden className="rounded-full bg-white/[.1] px-1.5 text-xs">
              {activeFilters}
            </span>
          )}
        </Button>
        {popup?.kind === 'filters' && (
          <Popover id={popoverId} label={t('Filters')} anchor={popup.anchor} onClose={() => setPopup(null)}>
            <LibraryFilters
              values={{ kind, source, format, collection: collectionFilter, smart: smartFilter, sort }}
              sources={sources}
              formats={formats}
              collections={collections}
              smartCollections={smartChoices}
              onChange={(change) => {
                if (change.kind !== undefined) setKind(change.kind)
                if (change.source !== undefined) setSource(change.source)
                if (change.format !== undefined) setFormat(change.format)
                if (change.collection !== undefined) setCollectionFilter(change.collection)
                if (change.smart !== undefined) setSmartFilter(change.smart)
                if (change.sort !== undefined) setSort(change.sort)
                setPage(0)
              }}
            />
            <div className="mt-4 flex justify-between gap-2">
              <Button
                variant="ghost"
                disabled={!hasFilters}
                onClick={(event) => {
                  resetFilters()
                  event.currentTarget
                    .closest('[role="dialog"]')
                    ?.querySelector('select')
                    ?.focus({ preventScroll: true })
                }}
              >
                {t('Reset filters')}
              </Button>
              <Button
                onClick={() => {
                  popup.anchor.focus({ preventScroll: true })
                  setPopup(null)
                }}
              >
                {t('Done')}
              </Button>
            </div>
          </Popover>
        )}
        <div className="segmented" role="group" aria-label={t('Library view')}>
          <button
            type="button"
            aria-label={t('Grid view')}
            aria-pressed={layout === 'grid'}
            onClick={() => chooseLayout('grid')}
          >
            <LayoutGrid aria-hidden size={16} />
          </button>
          <button
            type="button"
            aria-label={t('List view')}
            aria-pressed={layout === 'list'}
            onClick={() => chooseLayout('list')}
          >
            <List aria-hidden size={16} />
          </button>
        </div>
      </div>

      {filterSummary.length > 0 && (
        <div
          role="group"
          aria-label={t('Active filters')}
          className="flex min-w-0 flex-wrap gap-1.5 text-xs text-zinc-400"
        >
          {filterSummary.map(([label, value]) => (
            <span key={label} className="min-w-0 max-w-full break-all rounded-lg bg-white/[.05] px-2 py-1">
              {label}: {value}
            </span>
          ))}
        </div>
      )}

      {scan && (
        <div
          role="status"
          className={`library-scan ${scan.incomplete ? '' : 'library-scan-complete'} grid gap-1 text-xs text-zinc-400`}
        >
          <p>
            {t('Scanned {checked} entries; found {count} media files.', {
              checked: scan.checked,
              count: scan.media_count,
            })}
          </p>
          {scan.incomplete && (
            <div className="grid gap-1 text-amber-200">
              <p>{t('The library scan is incomplete. Search and filters cover discovered files only.')}</p>
              {scan.reasons.includes('entry_limit') && (
                <p>{t('Scan limit reached ({limit} entries).', { limit: scan.entry_limit })}</p>
              )}
              {scan.reasons.includes('depth_limit') && (
                <p>{t('Folders beyond {depth} directory levels were skipped.', { depth: scan.max_depth })}</p>
              )}
              {scan.reasons.includes('unreadable') && (
                <p>{t('Some files or folders could not be read. Check permissions and refresh.')}</p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="library-results-bar flex min-h-8 flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
        <span className="library-count">
          {hasFilters
            ? t(scan?.incomplete ? '{count} of {total} discovered files' : '{count} of {total} files', {
                count: shown.length,
                total: files.length,
              })
            : t(scan?.incomplete ? '{count} discovered files' : '{count} files', { count: files.length })}
        </span>
        {hasFilters && shown.length > 0 && popup?.kind !== 'filters' && (
          <button className="action-btn" onClick={resetFilters}>
            {t('Reset filters')}
          </button>
        )}
      </div>
      {audioPlayer && shownAudio.length > 0 && (
        <div
          className="compact-actions flex flex-wrap items-center gap-2"
          role="group"
          aria-label={t('Audio playback actions')}
        >
          <Button onClick={() => audioPlayer.playFiles(shownAudio.slice(0, AUDIO_QUEUE_LIMIT))}>
            <Play aria-hidden size={15} /> {t('Play filtered audio')} ·{' '}
            {Math.min(shownAudio.length, AUDIO_QUEUE_LIMIT)}
          </Button>
          <Button onClick={() => addAudio(shownAudio)}>
            <ListPlus aria-hidden size={15} /> {t('Add filtered audio to queue')}
          </Button>
          {shownAudio.length > AUDIO_QUEUE_LIMIT && (
            <span className="text-xs text-zinc-400">
              {t('Playback queues hold up to 500 tracks. Narrow your filters to choose fewer.')}
            </span>
          )}
        </div>
      )}
      {(hasFilters || page > 0 || pageSize !== 50) && (
        <div>
          <Button variant="ghost" disabled={busy} onClick={() => setBrowse({ ...DEFAULT_BROWSE })}>
            {t('Reset browsing')}
          </Button>
        </div>
      )}
      {(shown.length > 0 || chosen.length > 0) && (
        <div
          className="compact-actions library-selection flex flex-wrap items-center gap-2 text-xs"
          role="group"
          aria-label={t('Library selection')}
        >
          <Button
            disabled={busy || editingBlocked || visible.every((file) => selectedKeys.has(file.path))}
            onClick={selectPage}
          >
            {t('Select this page')}
          </Button>
          <span>
            {t('{count} selected', { count: chosen.length })} ·{' '}
            {formatBytes(chosen.reduce((sum, file) => sum + file.size, 0))}
          </span>
          <SelectionScope
            items={chosen.map((file) => ({ key: file.path, label: file.path }))}
            visible={visible.map((file) => file.path)}
            disabled={busy}
            onClear={() => setSelected([])}
            onRemove={(path) => setSelected((previous) => previous.filter((item) => item !== path))}
          />
          {chosen.length > 0 && (
            <>
              {audioPlayer && chosen.some(playableAudio) && (
                <Button disabled={busy} onClick={() => addAudio(chosen)}>
                  {t('Add selected audio to queue')}
                </Button>
              )}
              <Button
                disabled={busy}
                onClick={() =>
                  organize(
                    chosen.map((file) => file.path),
                    { favorite: true },
                  )
                }
              >
                {t('Favorite selected')}
              </Button>
              <Button
                disabled={busy}
                onClick={() => {
                  setOrganizing(chosen.map((file) => file.path))
                  setError('')
                }}
              >
                {t('Organize selected collections')}
              </Button>
              <Button
                disabled={busy || editingBlocked}
                onClick={() => {
                  setError('')
                  setBatchAction('trash')
                }}
              >
                {t('Move selected to recovery')}
              </Button>
            </>
          )}
        </div>
      )}
      {editingBlocked && (
        <p className="text-xs text-amber-200">
          {t('File editing is available when running downloads finish.')}
        </p>
      )}
      {error && !editing && !recoveryOpen && !organizing && !batchAction && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}

      {files.length === 0 ? (
        <div className="grid justify-items-center gap-3 rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          <p>{t(scan?.incomplete ? 'No media files found in scanned folders.' : 'No media files yet.')}</p>
          <p className="text-xs">
            {t(
              scan?.incomplete
                ? 'Review the scan warning above, then refresh to try again.'
                : 'Import local files or download a link to start your collection.',
            )}
          </p>
          {onNewDownload && <Button onClick={onNewDownload}>{t('Paste a link')}</Button>}
        </div>
      ) : shown.length === 0 ? (
        <div className="library-empty grid justify-items-center gap-3 rounded-xl bg-white/[.025] px-4 py-8 text-center text-sm text-zinc-400">
          <p className="font-medium text-zinc-100">{t('No files match these conditions.')}</p>
          <p className="text-xs">{t('Try another search or clear all conditions to see your files.')}</p>
          <Button onClick={resetFilters}>{t('Clear all conditions')}</Button>
        </div>
      ) : (
        <ul className={layout === 'grid' ? 'library-grid' : 'library-list grid gap-1'}>
          {visible.map((f) => (
            <li
              key={f.path}
              className="library-file flex flex-wrap items-center gap-3 rounded-xl px-2 py-3 hover:bg-white/[.03]"
            >
              {fileKind(f) === 'image' ? (
                <ImageThumbnail file={f} onPreview={() => previewImage(f)} />
              ) : (
                <MediaArtwork file={f} onOpen={() => setDetails({ file: f, autoPlay: false })} />
              )}
              <input
                type="checkbox"
                checked={selectedKeys.has(f.path)}
                disabled={busy || editingBlocked}
                aria-label={t('Select {name}', { name: f.name })}
                onChange={() => toggle(f.path)}
              />
              <div className="file-info min-w-0 flex-1 text-sm" title={f.path}>
                <button
                  className="block max-w-full truncate text-left font-medium"
                  title={f.name}
                  aria-label={t('Details for {name}', { name: f.name })}
                  onClick={() => setDetails({ file: f, autoPlay: false })}
                >
                  {layout === 'grid' && f.title ? f.title : displayFilename(f.name)}
                </button>
                {f.complete === false && (
                  <p className="mt-1 text-xs text-amber-300">
                    {t('Processing incomplete')} ·{' '}
                    {t(
                      f.can_repair
                        ? 'Repair this file using the files already downloaded.'
                        : 'Retry the original task to finish processing.',
                    )}
                  </p>
                )}
                <p className="mt-1 truncate text-xs text-zinc-500">
                  {f.source === 'local' ? t('Local file') : f.source || t('Unknown source')} · {f.path}
                </p>
                {!!f.tags?.length && (
                  <p className="mt-1 truncate text-xs text-emerald-300">{f.tags.join(' · ')}</p>
                )}
                {f.playback && (
                  <p className="mt-1 text-xs text-zinc-400">
                    {f.playback.finished
                      ? t('Finished playback')
                      : t('Continue at {time}', { time: formatDuration(f.playback.position) })}
                  </p>
                )}
              </div>
              <span className="hidden shrink-0 text-xs tabular-nums text-zinc-500 sm:inline">
                {formatBytes(f.size)}
              </span>
              <span className="hidden shrink-0 text-xs text-zinc-500 md:inline">
                {formatDate(f.downloaded ?? f.mtime)}
              </span>
              <div className="file-actions flex flex-wrap gap-1">
                <button
                  className="action-btn"
                  disabled={busy}
                  aria-pressed={!!f.favorite}
                  aria-label={t(f.favorite ? 'Unfavorite {name}' : 'Favorite {name}', { name: f.name })}
                  onClick={() => organize([f.path], { favorite: !f.favorite })}
                >
                  <Star aria-hidden size={13} className={f.favorite ? 'fill-amber-300 text-amber-300' : ''} />
                </button>
                {f.complete === false && f.can_repair && (
                  <Button disabled={busy || editingBlocked} onClick={() => requestRepair(f)}>
                    {t('Repair')}
                  </Button>
                )}
                {fileKind(f) === 'image' ? (
                  <button className="action-btn" onClick={() => previewImage(f)}>
                    <ImageIcon aria-hidden size={13} /> {t('Preview image')}
                  </button>
                ) : f.complete !== false ? (
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => {
                      if (fileKind(f) === 'audio' && audioPlayer) audioPlayer.playFile(f)
                      else setDetails({ file: f, autoPlay: true })
                    }}
                  >
                    <Play aria-hidden size={13} />
                    {t(fileKind(f) === 'audio' ? 'Play audio' : 'Play video')}
                  </button>
                ) : windowMode ? (
                  <button type="button" className="action-btn" onClick={() => openFile(f.path).catch(report)}>
                    <Play aria-hidden size={13} />{' '}
                    {t(f.complete === false ? 'Open' : fileKind(f) === 'audio' ? 'Play audio' : 'Play video')}
                  </button>
                ) : (
                  <a className="action-btn" href={fileUrl(f.path)} target="_blank" rel="noreferrer">
                    <Play aria-hidden size={13} />{' '}
                    {t(f.complete === false ? 'Open' : fileKind(f) === 'audio' ? 'Play audio' : 'Play video')}
                  </a>
                )}
                <button
                  type="button"
                  className="action-btn"
                  aria-label={t('More actions for {name}', { name: f.name })}
                  aria-haspopup="dialog"
                  aria-expanded={popup?.kind === 'file' && popup.path === f.path}
                  aria-controls={popup?.kind === 'file' && popup.path === f.path ? popoverId : undefined}
                  onClick={(event) => {
                    const anchor = event.currentTarget
                    setPopup((current) =>
                      current?.kind === 'file' && current.path === f.path
                        ? null
                        : { kind: 'file', path: f.path, anchor },
                    )
                  }}
                >
                  <Ellipsis aria-hidden size={16} /> {t('More')}
                </button>
                {popup?.kind === 'file' && popup.path === f.path && (
                  <Popover
                    id={popoverId}
                    label={t('More actions for {name}', { name: f.name })}
                    anchor={popup.anchor}
                    onClose={() => setPopup(null)}
                    actions
                  >
                    {audioPlayer && playableAudio(f) && (
                      <button className="action-btn" onClick={() => addAudio([f])}>
                        <ListPlus aria-hidden size={13} /> {t('Add to playback queue')}
                      </button>
                    )}
                    <button
                      className="action-btn"
                      disabled={busy}
                      aria-label={t('Manage collections for {name}', { name: f.name })}
                      onClick={() => {
                        setOrganizing([f.path])
                        setError('')
                      }}
                    >
                      <ListPlus aria-hidden size={13} /> {t('Organize collections')}
                    </button>
                    <a className="action-btn" href={fileUrl(f.path)} download={f.name}>
                      <Download aria-hidden size={13} /> {t('Download')}
                    </a>

                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => openFolder(f.path).catch(report)}
                      aria-label={t('Show {name} in folder', { name: f.name })}
                    >
                      <FolderOpen aria-hidden size={13} />
                      {t('Show in folder')}
                    </button>
                    {f.source_url && windowMode ? (
                      <button
                        className="action-btn"
                        aria-label={t('Open original page')}
                        onClick={() => openExternalUrl(f.source_url!).catch(report)}
                      >
                        <ExternalLink aria-hidden size={13} /> {t('Original page')}
                      </button>
                    ) : (
                      f.source_url && (
                        <a
                          className="action-btn"
                          href={f.source_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={t('Open original page')}
                        >
                          <ExternalLink aria-hidden size={13} /> {t('Original page')}
                        </a>
                      )
                    )}
                    <button
                      className="action-btn"
                      disabled={busy || editingBlocked}
                      aria-label={t('Rename {name}', { name: f.name })}
                      onClick={() => {
                        setError('')
                        setName(f.name)
                        setEditing({ kind: 'rename', file: f })
                      }}
                    >
                      <Pencil aria-hidden size={13} /> {t('Rename')}
                    </button>
                    <button
                      className="action-btn"
                      disabled={busy || editingBlocked}
                      aria-label={t('Move {name} to recovery', { name: f.name })}
                      data-danger
                      onClick={() => {
                        setError('')
                        setEditing({ kind: 'trash', file: f })
                      }}
                    >
                      <Trash2 aria-hidden size={13} /> {t('Move to recovery')}
                    </button>
                  </Popover>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {shown.length > 0 && (
        <div
          className="flex flex-wrap items-center justify-end gap-3 text-xs"
          role="group"
          aria-label={t('Library pagination')}
        >
          <label className="flex items-center gap-2">
            {t('Files per page')}
            <select
              className="field !w-auto"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(0)
              }}
            >
              {[25, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <span>
            {t('Showing {from}–{to} of {count}', {
              from: currentPage * pageSize + 1,
              to: Math.min((currentPage + 1) * pageSize, shown.length),
              count: shown.length,
            })}
          </span>
          <Button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
            {t('Previous')}
          </Button>
          <span>
            {currentPage + 1} / {Math.ceil(shown.length / pageSize)}
          </span>
          <Button
            disabled={(currentPage + 1) * pageSize >= shown.length}
            onClick={() => setPage(currentPage + 1)}
          >
            {t('Next')}
          </Button>
        </div>
      )}
      {details && (
        <MediaDetails
          audioPlayer={audioPlayer}
          key={details.file.path}
          file={files.find((file) => file.path === details.file.path) || details.file}
          collections={collections}
          autoPlay={details.autoPlay}
          windowMode={windowMode}
          onClose={() => setDetails(null)}
          onRefresh={onRefresh}
          onToast={onToast}
        />
      )}
      <Modal
        open={organizing !== null}
        title={t('Organize collections')}
        onClose={() => {
          if (!busy) setOrganizing(null)
        }}
      >
        <div className="grid gap-3">
          <p className="text-sm">{t('{count} selected', { count: organizing?.length ?? 0 })}</p>
          <p className="text-xs text-zinc-400">
            {t('Adding to or removing from a collection keeps the files in their current location.')}
          </p>
          {collections.length === 0 && <p>{t('Create a collection using Manage collections.')}</p>}
          {collections.map((collection) => {
            const members = (organizing ?? []).filter((path) =>
              files.find((file) => file.path === path)?.collections?.includes(collection.id),
            ).length
            return (
              <div key={collection.id} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 break-words">
                  {collection.name} · {members}/{organizing?.length ?? 0}
                </span>
                <Button
                  disabled={busy || members === organizing?.length}
                  onClick={() => organize(organizing ?? [], { collection_id: collection.id })}
                  aria-label={t('Add to {name}', { name: collection.name })}
                >
                  {t('Add')}
                </Button>
                <Button
                  disabled={busy || members === 0}
                  onClick={() => organize(organizing ?? [], { collection_id: collection.id, remove: true })}
                  aria-label={t('Remove from {name}', { name: collection.name })}
                >
                  {t('Remove from collection')}
                </Button>
              </div>
            )
          })}
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <Button disabled={busy} onClick={() => setOrganizing(null)}>
            {t('Done')}
          </Button>
        </div>
      </Modal>
      <Modal open={picture !== null} title={t('Image preview')} wide onClose={() => setPicture(null)}>
        {picture && (
          <div className="grid gap-3">
            <p className="break-all text-sm">{picture.name}</p>
            <p className="text-xs text-zinc-400">
              {formatBytes(picture.size)}
              {dimensions && ` · ${dimensions}`}
            </p>
            <div className="max-h-[60vh] overflow-auto rounded-xl bg-black/30">
              {imageFailed ? (
                <p role="alert" className="p-4 text-sm text-amber-200">
                  {t('This image cannot be displayed here. Open the original file instead.')}
                </p>
              ) : (
                <img
                  key={picture.path}
                  src={fileUrl(picture.path)}
                  alt={picture.name}
                  className={originalSize ? 'max-w-none' : 'mx-auto max-h-[60vh] max-w-full object-contain'}
                  onLoad={(e) =>
                    setDimensions(`${e.currentTarget.naturalWidth} × ${e.currentTarget.naturalHeight}`)
                  }
                  onError={() => setImageFailed(true)}
                />
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={imageFailed} onClick={() => setOriginalSize(!originalSize)}>
                {t(originalSize ? 'Fit to window' : 'Original size')}
              </Button>
              <a className="action-btn" href={fileUrl(picture.path)} download={picture.name}>
                {t('Download')}
              </a>
              <Button onClick={() => openFile(picture.path).catch(report)}>{t('Open')}</Button>
              <Button onClick={() => openFolder(picture.path).catch(report)}>{t('Show in folder')}</Button>
              {picture.source_url &&
                (windowMode ? (
                  <Button onClick={() => openExternalUrl(picture.source_url!).catch(report)}>
                    {t('Open original page')}
                  </Button>
                ) : (
                  <a className="action-btn" href={picture.source_url} target="_blank" rel="noreferrer">
                    {t('Open original page')}
                  </a>
                ))}
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={editing !== null}
        title={t(editing?.kind === 'rename' ? 'Rename file' : 'Move to recovery')}
        onClose={() => {
          if (!busy) setEditing(null)
        }}
      >
        {editing && (
          <div className="grid gap-4">
            <p className="break-all text-sm text-zinc-300">{editing.file.path}</p>
            <p className="text-xs text-zinc-400">
              {t('Matching subtitles and cover files are managed together with this file.')}
            </p>
            {editing.kind === 'rename' ? (
              <label className="control">
                <span>{t('Filename')}</span>
                <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
                <span>{t('Keep the original file extension.')}</span>
              </label>
            ) : (
              <p className="text-sm text-zinc-400">
                {t('The file is moved to a recovery folder. You can restore it from Library > Recovery.')}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-300">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button disabled={busy} onClick={() => setEditing(null)}>
                {t('Cancel')}
              </Button>
              <Button
                variant="primary"
                disabled={
                  busy ||
                  editingBlocked ||
                  (editing.kind === 'rename' && (!name.trim() || name === editing.file.name))
                }
                onClick={editFile}
              >
                {t(editing.kind === 'rename' ? 'Save' : 'Move to recovery')}
              </Button>
            </div>
          </div>
        )}
      </Modal>
      <Modal
        open={batchAction === 'trash'}
        title={t('Move selected to recovery')}
        onClose={() => {
          if (!busy) setBatchAction(null)
        }}
      >
        <div className="grid gap-3">
          <p>
            {t('Move {count} files and their matching subtitles and covers to Recovery?', {
              count: chosen.length,
            })}
          </p>
          <p className="text-sm text-zinc-400">
            {t('You can restore them later.')} ·{' '}
            {formatBytes(chosen.reduce((sum, file) => sum + file.size, 0))}
          </p>
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button disabled={busy} onClick={() => setBatchAction(null)}>
              {t('Cancel')}
            </Button>
            <Button
              disabled={busy || editingBlocked || chosen.length === 0}
              onClick={() => changeMany('trash')}
            >
              {t('Confirm move')}
            </Button>
          </div>
        </div>
      </Modal>
      <Modal
        open={recoveryOpen}
        title={t('Recovery')}
        onClose={() => {
          if (!busy) {
            setRecoveryOpen(false)
            setBatchAction(null)
            setDeleting(null)
            setError('')
          }
        }}
      >
        <div className="grid gap-3">
          <p className="text-sm text-zinc-400">
            {t('Recovery files stay on disk until restored or permanently deleted.')}
          </p>
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          {!deleting && batchAction !== 'purge' && recovery.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Button
                disabled={busy || editingBlocked}
                onClick={() =>
                  setRecoverySelected(
                    recoveryChosen.length === recovery.length ? [] : recovery.map((file) => file.id),
                  )
                }
              >
                {t(recoveryChosen.length === recovery.length ? 'Clear selection' : 'Select all')}
              </Button>
              <span>
                {t('{count} selected', { count: recoveryChosen.length })} ·{' '}
                {formatBytes(recoveryChosen.reduce((sum, file) => sum + (file.size || 0), 0))}
              </span>
              <Button
                disabled={busy || editingBlocked || !recoveryChosen.length}
                onClick={() => changeMany('restore')}
              >
                {t('Restore selected')}
              </Button>
              <Button
                disabled={busy || editingBlocked || !recoveryChosen.length}
                onClick={() => {
                  setError('')
                  setBatchAction('purge')
                }}
              >
                {t('Delete selected permanently')}
              </Button>
            </div>
          )}
          {batchAction === 'purge' && (
            <div className="grid gap-3">
              <p>
                {t(
                  'Permanently delete {count} files and their matching subtitles and covers? This cannot be undone.',
                  { count: recoveryChosen.length },
                )}
              </p>
              <p>
                {t('Space to free')} ·{' '}
                {formatBytes(recoveryChosen.reduce((sum, file) => sum + (file.size || 0), 0))}
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  disabled={busy}
                  onClick={() => {
                    setBatchAction(null)
                    setError('')
                  }}
                >
                  {t('Cancel')}
                </Button>
                <Button
                  disabled={busy || editingBlocked || !recoveryChosen.length}
                  onClick={() => changeMany('purge')}
                >
                  {t('Confirm permanent deletion')}
                </Button>
              </div>
            </div>
          )}
          {deleting && (
            <div className="grid gap-3">
              <p className="break-all text-sm">{deleting.path}</p>
              <p className="text-sm text-red-300">
                {t(
                  'Permanently delete this file and its matching subtitles and covers? This cannot be undone.',
                )}
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  disabled={busy}
                  onClick={() => {
                    setDeleting(null)
                    setError('')
                  }}
                >
                  {t('Cancel')}
                </Button>
                <Button disabled={busy || editingBlocked} onClick={removeRecovery}>
                  {t('Confirm permanent deletion')}
                </Button>
              </div>
            </div>
          )}
          {busy && <p role="status">{t('Loading…')}</p>}
          {!busy && recovery.length === 0 && (
            <p className="text-sm text-zinc-400">{t('No recovery files.')}</p>
          )}
          {!deleting &&
            batchAction !== 'purge' &&
            recovery.map((item) => (
              <div key={item.id} className="flex items-center gap-3 rounded-xl bg-white/[.025] p-3">
                <input
                  type="checkbox"
                  checked={recoveryKeys.has(item.id)}
                  disabled={busy || editingBlocked}
                  aria-label={t('Select {name}', { name: item.path })}
                  onChange={() => toggle(item.id, true)}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm" title={item.path}>
                    {displayFilename(item.path.split(/[\\/]/).pop() || item.path)}
                  </p>
                  <p className="text-xs text-zinc-500">{formatDate(item.removed)}</p>
                </div>
                <Button disabled={busy || editingBlocked} onClick={() => restore(item.id)}>
                  {t('Restore')}
                </Button>
                <Button
                  disabled={busy || editingBlocked}
                  onClick={() => {
                    setError('')
                    setDeleting(item)
                  }}
                >
                  <Trash2 aria-hidden size={14} /> {t('Delete permanently')}
                </Button>
              </div>
            ))}
        </div>
      </Modal>
    </section>
  )
}
