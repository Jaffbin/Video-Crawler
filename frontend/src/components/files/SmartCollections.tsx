import { useMemo, useState } from 'react'
import { changeSmartCollection } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import { BUILTIN_SMART_COLLECTIONS, matchesSmartCollection, smartName } from '../../lib/smartCollections'
import type { FileItem, SmartCollection, SmartRules } from '../../types/api'
import { Button } from '../ui/Button'

export function SmartCollections({
  files,
  collections,
  onRefresh,
  onToast,
  onView,
  onBusyChange,
}: {
  files: FileItem[]
  collections: SmartCollection[]
  onRefresh: () => void
  onToast: ToastFn
  onView?: (id: string) => void
  onBusyChange?: (busy: boolean) => void
}) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [rules, setRules] = useState<SmartRules>({})
  const [editing, setEditing] = useState<string>()
  const [deleting, setDeleting] = useState<SmartCollection | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sources = useMemo(
    () =>
      [
        ...new Set([
          ...files.map((file) => file.source || 'unknown'),
          ...(rules.source ? [rules.source] : []),
        ]),
      ].sort(),
    [files, rules.source],
  )
  const formats = useMemo(
    () =>
      [
        ...new Set([
          ...files.map((file) => '.' + file.name.split('.').pop()!.toLowerCase()),
          ...(rules.format ? [rules.format] : []),
        ]),
      ].sort(),
    [files, rules.format],
  )
  const savedRules = useMemo(() => {
    const result = { ...rules }
    if (result.tag !== undefined) {
      if (result.tag.trim()) result.tag = result.tag.trim()
      else delete result.tag
    }
    return result
  }, [rules])
  const preview = useMemo(
    () => files.filter((file) => matchesSmartCollection(file, savedRules)).length,
    [files, savedRules],
  )
  const hasRules = Object.keys(savedRules).length > 0
  function patch<K extends keyof SmartRules>(key: K, value: SmartRules[K] | '') {
    setRules((before) => {
      const next = { ...before }
      if (value === '' || value === undefined) delete next[key]
      else next[key] = value
      return next
    })
  }
  function reset() {
    setName('')
    setRules({})
    setEditing(undefined)
    setDeleting(null)
    setError('')
  }
  async function save(action: 'create' | 'update' | 'delete') {
    setBusy(true)
    onBusyChange?.(true)
    setError('')
    try {
      await changeSmartCollection(
        action,
        action === 'delete' ? undefined : name.trim(),
        action === 'delete' ? deleting?.id : editing,
        action === 'delete' ? undefined : savedRules,
      )
      reset()
      onRefresh()
      onToast(t('Smart collections updated'))
    } catch (error) {
      setError(t(error instanceof Error ? error.message : 'That did not work'))
    } finally {
      setBusy(false)
      onBusyChange?.(false)
    }
  }
  return (
    <div className="grid gap-4">
      <p className="text-sm text-zinc-400">
        {t(
          'Smart collections update automatically when files match all their rules. Files stay in their current location.',
        )}
      </p>
      <section className="grid gap-2" aria-label={t('Built-in smart collections')}>
        <h3 className="text-sm font-semibold">{t('Built-in smart collections')}</h3>
        <div className="flex flex-wrap gap-2">
          {BUILTIN_SMART_COLLECTIONS.map((collection) => (
            <Button key={collection.id} disabled={!onView || busy} onClick={() => onView?.(collection.id)}>
              {smartName(collection, t)}
            </Button>
          ))}
        </div>
      </section>
      <section className="grid gap-2" aria-label={t('My smart collections')}>
        <h3 className="text-sm font-semibold">{t('My smart collections')}</h3>
        {collections.length === 0 && (
          <p className="text-sm text-zinc-400">{t('Create your first smart collection below.')}</p>
        )}
        <ul className="grid max-h-[25vh] gap-2 overflow-auto">
          {collections.map((collection) => (
            <li key={collection.id} className="flex flex-wrap items-center gap-2 rounded-lg bg-white/5 p-2">
              <span className="min-w-0 flex-1 break-words">{collection.name}</span>
              {onView && (
                <Button
                  disabled={busy}
                  aria-label={t('View smart collection {name}', { name: collection.name })}
                  onClick={() => onView(collection.id)}
                >
                  {t('View')}
                </Button>
              )}
              <Button
                disabled={busy}
                aria-label={t('Edit smart collection {name}', { name: collection.name })}
                onClick={() => {
                  setEditing(collection.id)
                  setName(collection.name)
                  setRules({ ...collection.rules })
                  setDeleting(null)
                  setError('')
                }}
              >
                {t('Edit rules')}
              </Button>
              <Button
                disabled={busy}
                aria-label={t('Delete smart collection {name}', { name: collection.name })}
                onClick={() => {
                  setDeleting(collection)
                  setError('')
                }}
              >
                {t('Delete collection')}
              </Button>
            </li>
          ))}
        </ul>
      </section>
      {deleting ? (
        <div className="grid gap-3 rounded-xl bg-white/5 p-3">
          <p>{t('Delete collection {name}? Files and favorites will be kept.', { name: deleting.name })}</p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setDeleting(null)}>
              {t('Cancel')}
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => save('delete')}>
              {t('Confirm delete collection')}
            </Button>
          </div>
        </div>
      ) : (
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            void save(editing ? 'update' : 'create')
          }}
        >
          <label className="control">
            <span>{t('Smart collection name')}</span>
            <input
              className="field"
              value={name}
              maxLength={80}
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <fieldset disabled={busy} className="grid min-w-0 gap-3 sm:grid-cols-2">
            <legend className="mb-3 text-sm font-semibold">{t('Match all conditions')}</legend>
            <label className="control">
              <span>{t('Media type')}</span>
              <select
                className="field"
                value={rules.kind || ''}
                onChange={(event) => patch('kind', event.target.value as SmartRules['kind'])}
              >
                <option value="">{t('Any media type')}</option>
                <option value="video">{t('Videos')}</option>
                <option value="audio">{t('Audio')}</option>
                <option value="image">{t('Images')}</option>
              </select>
            </label>
            <label className="control">
              <span>{t('Source site')}</span>
              <select
                className="field"
                value={rules.source || ''}
                onChange={(event) => patch('source', event.target.value)}
              >
                <option value="">{t('Any source')}</option>
                {sources.map((source) => (
                  <option key={source} value={source}>
                    {source === 'unknown'
                      ? t('Unknown source')
                      : source === 'local'
                        ? t('Local file')
                        : source}
                  </option>
                ))}
              </select>
            </label>
            <label className="control">
              <span>{t('Format')}</span>
              <select
                className="field"
                value={rules.format || ''}
                onChange={(event) => patch('format', event.target.value)}
              >
                <option value="">{t('Any format')}</option>
                {formats.map((format) => (
                  <option key={format} value={format}>
                    {format.slice(1).toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
            <label className="control">
              <span>{t('Tag matches')}</span>
              <input
                className="field"
                maxLength={40}
                value={rules.tag || ''}
                onChange={(event) => patch('tag', event.target.value)}
              />
            </label>
            <label className="control">
              <span>{t('Favorite status')}</span>
              <select
                className="field"
                value={rules.favorite === undefined ? '' : String(rules.favorite)}
                onChange={(event) =>
                  patch('favorite', event.target.value === '' ? '' : event.target.value === 'true')
                }
              >
                <option value="">{t('Any favorite status')}</option>
                <option value="true">{t('Favorites only')}</option>
                <option value="false">{t('Not favorited')}</option>
              </select>
            </label>
            <label className="control">
              <span>{t('Saved within the last')}</span>
              <select
                className="field"
                value={rules.recent_days || ''}
                onChange={(event) =>
                  patch('recent_days', event.target.value ? Number(event.target.value) : '')
                }
              >
                <option value="">{t('Any time')}</option>
                {[...new Set([7, 30, 90, 365, ...(rules.recent_days ? [rules.recent_days] : [])])]
                  .sort((a, b) => a - b)
                  .map((days) => (
                    <option key={days} value={days}>
                      {t('{count} days', { count: days })}
                    </option>
                  ))}
              </select>
            </label>
            <label className="control">
              <span>{t('Playback status')}</span>
              <select
                className="field"
                value={rules.playback || ''}
                onChange={(event) => patch('playback', event.target.value as SmartRules['playback'])}
              >
                <option value="">{t('Any playback status')}</option>
                <option value="unplayed">{t('Not started in this app')}</option>
                <option value="in_progress">{t('In progress')}</option>
                <option value="finished">{t('Finished playback')}</option>
              </select>
            </label>
          </fieldset>
          <p className="text-xs text-zinc-400">
            {t(
              'Playback rules use this app’s records for completed video/audio downloads. Older files use modification time when no saved date exists.',
            )}
          </p>
          <p role="status">
            {hasRules
              ? t('{count} files currently match', { count: preview })
              : t('Choose at least one condition to preview matches.')}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" type="submit" disabled={busy || !name.trim() || !hasRules}>
              {t(editing ? 'Save smart collection' : 'Create smart collection')}
            </Button>
            <Button disabled={busy} onClick={reset}>
              {t('Clear rules')}
            </Button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
    </div>
  )
}
