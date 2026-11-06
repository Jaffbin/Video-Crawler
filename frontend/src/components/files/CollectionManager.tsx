import { useState } from 'react'
import { changeCollection } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import type { FileItem, LibraryCollection, SmartCollection } from '../../types/api'
import { SmartCollections } from './SmartCollections'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

export function CollectionManager({
  collections,
  onRefresh,
  onToast,
  files = [],
  smartCollections = [],
  onViewSmart,
}: {
  collections: LibraryCollection[]
  onRefresh: () => void
  onToast: ToastFn
  files?: FileItem[]
  smartCollections?: SmartCollection[]
  onViewSmart?: (id: string) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'manual' | 'smart'>('manual')
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<string | undefined>()
  const [deleting, setDeleting] = useState<LibraryCollection | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function save(action: 'create' | 'rename' | 'delete') {
    setBusy(true)
    setError('')
    try {
      await changeCollection(
        action,
        action === 'delete' ? undefined : name.trim(),
        action === 'delete' ? deleting?.id : editing,
      )
      setEditing(undefined)
      setDeleting(null)
      setName('')
      onRefresh()
      onToast(t('Collections updated'))
    } catch (e) {
      setError(t(e instanceof Error ? e.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button
        variant="ghost"
        onClick={() => {
          setOpen(true)
          setError('')
          setDeleting(null)
          setTab('manual')
        }}
      >
        {t('Manage collections')}
      </Button>
      <Modal
        open={open}
        title={t('Manage collections')}
        onClose={() => {
          if (!busy) setOpen(false)
        }}
      >
        <div role="group" aria-label={t('Collection type')} className="mb-4 flex flex-wrap gap-2">
          <Button
            variant={tab === 'manual' ? 'primary' : 'ghost'}
            aria-pressed={tab === 'manual'}
            disabled={busy}
            onClick={() => setTab('manual')}
          >
            {t('Manual collections')}
          </Button>
          <Button
            variant={tab === 'smart' ? 'primary' : 'ghost'}
            aria-pressed={tab === 'smart'}
            disabled={busy}
            onClick={() => setTab('smart')}
          >
            {t('Smart collections')}
          </Button>
        </div>
        {tab === 'smart' ? (
          <SmartCollections
            files={files}
            collections={smartCollections}
            onRefresh={onRefresh}
            onToast={onToast}
            onBusyChange={setBusy}
            onView={
              onViewSmart
                ? (id) => {
                    onViewSmart(id)
                    setOpen(false)
                  }
                : undefined
            }
          />
        ) : (
          <div className="grid gap-4">
            <p className="text-xs text-zinc-400">
              {t(
                'Collections organize files without moving or copying them. A file can belong to several collections.',
              )}
            </p>
            <ul className="grid max-h-[35vh] gap-2 overflow-y-auto">
              {collections.map((collection) => (
                <li key={collection.id} className="flex items-center gap-2">
                  <span className="min-w-0 flex-1 break-words">{collection.name}</span>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      setEditing(collection.id)
                      setName(collection.name)
                      setDeleting(null)
                      setError('')
                    }}
                  >
                    {t('Rename')}
                  </Button>
                  <Button
                    disabled={busy}
                    onClick={() => {
                      setDeleting(collection)
                      setError('')
                    }}
                    aria-label={t('Delete collection {name}', { name: collection.name })}
                  >
                    {t('Delete collection')}
                  </Button>
                </li>
              ))}
            </ul>
            {deleting ? (
              <div className="grid gap-3 rounded-xl bg-white/5 p-3">
                <p className="break-words">
                  {t('Delete collection {name}? Files and favorites will be kept.', { name: deleting.name })}
                </p>
                <div className="flex gap-2">
                  <Button disabled={busy} onClick={() => setDeleting(null)}>
                    {t('Cancel')}
                  </Button>
                  <Button disabled={busy} onClick={() => save('delete')}>
                    {t('Confirm delete collection')}
                  </Button>
                </div>
              </div>
            ) : (
              <form
                className="grid gap-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  void save(editing ? 'rename' : 'create')
                }}
              >
                <label className="control">
                  <span>{t('Collection name')}</span>
                  <input
                    className="field"
                    value={name}
                    maxLength={80}
                    disabled={busy}
                    onChange={(event) => setName(event.target.value)}
                  />
                </label>
                <div className="flex gap-2">
                  <Button type="submit" disabled={busy || !name.trim()}>
                    {t(editing ? 'Save collection name' : 'Create collection')}
                  </Button>
                  {editing && (
                    <Button
                      disabled={busy}
                      onClick={() => {
                        setEditing(undefined)
                        setName('')
                      }}
                    >
                      {t('Cancel rename')}
                    </Button>
                  )}
                </div>
              </form>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-300">
                {error}
              </p>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
