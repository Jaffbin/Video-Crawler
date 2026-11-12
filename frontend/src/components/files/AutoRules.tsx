import { useEffect, useId, useMemo, useState } from 'react'
import { changeAutoRule, getAutoRules } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import type { AutoRule, FileItem, LibraryCollection } from '../../types/api'
import { Button } from '../ui/Button'

type Draft = {
  name: string
  source: string
  kind: '' | 'video' | 'audio' | 'image'
  format: string
  tags: string
  collections: string[]
  favorite: boolean
  enabled: boolean
}

const EMPTY: Draft = {
  name: '',
  source: '',
  kind: '',
  format: '',
  tags: '',
  collections: [],
  favorite: false,
  enabled: true,
}

const KIND_LABELS = { video: 'Videos', audio: 'Audio', image: 'Images' } as const

function toDraft(rule: AutoRule): Draft {
  return {
    name: rule.name,
    source: rule.conditions.source ?? '',
    kind: rule.conditions.kind ?? '',
    format: rule.conditions.format ?? '',
    tags: (rule.actions.tags ?? []).join(', '),
    collections: rule.actions.collections ?? [],
    favorite: !!rule.actions.favorite,
    enabled: rule.enabled,
  }
}

function toRule(draft: Draft): Omit<AutoRule, 'id'> {
  const conditions: AutoRule['conditions'] = {}
  if (draft.source.trim()) conditions.source = draft.source.trim()
  if (draft.kind) conditions.kind = draft.kind
  if (draft.format.trim()) conditions.format = draft.format.trim()
  const actions: AutoRule['actions'] = {}
  const tags = draft.tags
    .split(/[,，]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
  if (tags.length) actions.tags = tags
  if (draft.collections.length) actions.collections = draft.collections
  if (draft.favorite) actions.favorite = true
  return { name: draft.name.trim(), enabled: draft.enabled, conditions, actions }
}

/**
 * Rules that tag new downloads, add them to collections or mark them as favorites.
 * The backend applies them when a download is saved; files already in the Library are not changed.
 */
export function AutoRules({
  files,
  collections,
  onToast,
  onBusyChange,
}: {
  files: FileItem[]
  collections: LibraryCollection[]
  onToast: ToastFn
  onBusyChange?: (busy: boolean) => void
}) {
  const { t } = useI18n()
  const listId = useId()
  const [rules, setRules] = useState<AutoRule[] | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [editing, setEditing] = useState<string>()
  const [deleting, setDeleting] = useState<AutoRule | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let stop = false
    getAutoRules()
      .then((result) => {
        if (!stop) setRules(result.auto_rules)
      })
      .catch((reason) => {
        if (!stop) setError(t(reason instanceof Error ? reason.message : 'That did not work'))
      })
    return () => {
      stop = true
    }
  }, [t])

  const sources = useMemo(
    () =>
      [...new Set(files.map((file) => file.source || '').filter((source) => source.includes('.')))].sort(),
    [files],
  )
  const formats = useMemo(
    () => [...new Set(files.map((file) => '.' + file.name.split('.').pop()!.toLowerCase()))].sort(),
    [files],
  )
  const collectionNames = useMemo(
    () => new Map(collections.map((collection) => [collection.id, collection.name])),
    [collections],
  )
  const candidate = toRule(draft)
  const ready =
    !!candidate.name &&
    Object.keys(candidate.conditions).length > 0 &&
    Object.keys(candidate.actions).length > 0

  function reset() {
    setDraft(EMPTY)
    setEditing(undefined)
    setDeleting(null)
    setError('')
  }

  async function send(action: 'create' | 'update' | 'delete', id?: string, rule?: Omit<AutoRule, 'id'>) {
    setBusy(true)
    onBusyChange?.(true)
    setError('')
    try {
      const result = await changeAutoRule(action, id, rule)
      setRules(result.auto_rules)
      onToast(t('Auto rules updated'))
      return true
    } catch (reason) {
      setError(t(reason instanceof Error ? reason.message : 'That did not work'))
      return false
    } finally {
      setBusy(false)
      onBusyChange?.(false)
    }
  }

  function describeWhen(rule: AutoRule) {
    const parts = []
    if (rule.conditions.source) parts.push(rule.conditions.source)
    if (rule.conditions.kind) parts.push(t(KIND_LABELS[rule.conditions.kind]))
    if (rule.conditions.format) parts.push(rule.conditions.format.slice(1).toUpperCase())
    return parts.join(', ')
  }

  function describeThen(rule: AutoRule) {
    const parts = []
    if (rule.actions.tags?.length) parts.push(t('tags {tags}', { tags: rule.actions.tags.join(', ') }))
    for (const id of rule.actions.collections ?? [])
      parts.push(t('collection {name}', { name: collectionNames.get(id) ?? '' }))
    if (rule.actions.favorite) parts.push(t('favorite'))
    return parts.join(', ')
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((before) => ({ ...before, [key]: value }))

  return (
    <div className="grid gap-4">
      <p className="text-sm text-zinc-400">
        {t(
          'When a download finishes, every rule whose conditions all match adds its tags, collections or favorite. Files are never moved, and files already in the Library are not changed.',
        )}
      </p>
      <section className="grid gap-2" aria-label={t('My auto rules')}>
        <h3 className="text-sm font-semibold">{t('My auto rules')}</h3>
        {rules?.length === 0 && (
          <p className="text-sm text-zinc-400">{t('Create your first auto rule below.')}</p>
        )}
        <ul className="grid max-h-[25vh] gap-2 overflow-auto">
          {(rules ?? []).map((rule) => (
            <li key={rule.id} className="grid gap-2 rounded-lg bg-white/5 p-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 break-words font-medium">
                  {rule.name}
                  {!rule.enabled && <span className="font-normal text-zinc-400"> ({t('off')})</span>}
                </span>
                <Button
                  disabled={busy}
                  aria-label={t(rule.enabled ? 'Turn off auto rule {name}' : 'Turn on auto rule {name}', {
                    name: rule.name,
                  })}
                  onClick={() => {
                    const { id, ...rest } = rule
                    void send('update', id, { ...rest, enabled: !rule.enabled })
                  }}
                >
                  {t(rule.enabled ? 'Turn off' : 'Turn on')}
                </Button>
                <Button
                  disabled={busy}
                  aria-label={t('Edit auto rule {name}', { name: rule.name })}
                  onClick={() => {
                    setEditing(rule.id)
                    setDraft(toDraft(rule))
                    setDeleting(null)
                    setError('')
                  }}
                >
                  {t('Edit')}
                </Button>
                <Button
                  disabled={busy}
                  aria-label={t('Delete auto rule {name}', { name: rule.name })}
                  onClick={() => {
                    setDeleting(rule)
                    setError('')
                  }}
                >
                  {t('Delete')}
                </Button>
              </div>
              <p className="text-xs text-zinc-400">
                {t('When {when}, add {then}.', { when: describeWhen(rule), then: describeThen(rule) })}
              </p>
            </li>
          ))}
        </ul>
      </section>
      {deleting ? (
        <div className="grid gap-3 rounded-xl bg-white/5 p-3">
          <p className="break-words">
            {t('Delete auto rule {name}? Tags and collections it already added are kept.', {
              name: deleting.name,
            })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setDeleting(null)}>
              {t('Cancel')}
            </Button>
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                if (await send('delete', deleting.id)) reset()
              }}
            >
              {t('Delete auto rule')}
            </Button>
          </div>
        </div>
      ) : (
        <form
          className="grid gap-3"
          onSubmit={async (event) => {
            event.preventDefault()
            if (await send(editing ? 'update' : 'create', editing, candidate)) reset()
          }}
        >
          <label className="control">
            <span>{t('Rule name')}</span>
            <input
              className="field"
              value={draft.name}
              maxLength={80}
              disabled={busy}
              onChange={(event) => set('name', event.target.value)}
            />
          </label>
          <fieldset disabled={busy} className="grid min-w-0 gap-3 sm:grid-cols-3">
            <legend className="mb-3 text-sm font-semibold">{t('When a new download matches all of')}</legend>
            <label className="control">
              <span>{t('Source site')}</span>
              <input
                className="field"
                list={`${listId}-sources`}
                placeholder="bilibili.com"
                value={draft.source}
                maxLength={200}
                onChange={(event) => set('source', event.target.value)}
              />
              <datalist id={`${listId}-sources`}>
                {sources.map((source) => (
                  <option key={source} value={source} />
                ))}
              </datalist>
            </label>
            <label className="control">
              <span>{t('Media type')}</span>
              <select
                className="field"
                value={draft.kind}
                onChange={(event) => set('kind', event.target.value as Draft['kind'])}
              >
                <option value="">{t('Any media type')}</option>
                <option value="video">{t('Videos')}</option>
                <option value="audio">{t('Audio')}</option>
                <option value="image">{t('Images')}</option>
              </select>
            </label>
            <label className="control">
              <span>{t('Format')}</span>
              <input
                className="field"
                list={`${listId}-formats`}
                placeholder=".mp3"
                value={draft.format}
                maxLength={11}
                onChange={(event) => set('format', event.target.value)}
              />
              <datalist id={`${listId}-formats`}>
                {formats.map((format) => (
                  <option key={format} value={format} />
                ))}
              </datalist>
            </label>
          </fieldset>
          <fieldset disabled={busy} className="grid min-w-0 gap-3">
            <legend className="mb-3 text-sm font-semibold">{t('Then')}</legend>
            <label className="control">
              <span>{t('Add tags (separate with commas)')}</span>
              <input
                className="field"
                value={draft.tags}
                onChange={(event) => set('tags', event.target.value)}
              />
            </label>
            {collections.length > 0 ? (
              <div className="grid gap-1" role="group" aria-label={t('Add to collections')}>
                <span className="text-sm text-zinc-300">{t('Add to collections')}</span>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {collections.map((collection) => (
                    <label key={collection.id} className="toggle-row">
                      <input
                        type="checkbox"
                        checked={draft.collections.includes(collection.id)}
                        onChange={(event) =>
                          set(
                            'collections',
                            event.target.checked
                              ? [...draft.collections, collection.id]
                              : draft.collections.filter((id) => id !== collection.id),
                          )
                        }
                      />
                      <span>{collection.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-400">
                {t('Create a manual collection first to add downloads to it automatically.')}
              </p>
            )}
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={draft.favorite}
                onChange={(event) => set('favorite', event.target.checked)}
              />
              <span>{t('Mark as favorite')}</span>
            </label>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" type="submit" disabled={busy || !ready}>
              {t(editing ? 'Save auto rule' : 'Create auto rule')}
            </Button>
            <Button disabled={busy} onClick={reset}>
              {t(editing ? 'Cancel editing' : 'Clear')}
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
