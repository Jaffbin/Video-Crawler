import { DatabaseZap } from 'lucide-react'
import { useState } from 'react'
import { checkLibraryData, repairLibraryData, type LibraryIntegrity } from '../../api/client'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'

/**
 * Checks the library database against its saved copy and offers the one repair that applies.
 * Nothing is repaired without a click, and a damaged database is kept, not deleted.
 */
export function LibraryDataCheck({ onRepaired }: { onRepaired?: () => void }) {
  const { t } = useI18n()
  const [report, setReport] = useState<LibraryIntegrity | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState('')

  async function run(task: () => Promise<LibraryIntegrity>, repaired = false) {
    setBusy(true)
    setError('')
    try {
      setReport(await task())
      setConfirming(false)
      if (repaired) onRepaired?.()
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : t('That did not work'))
    } finally {
      setBusy(false)
    }
  }

  function summary(value: LibraryIntegrity) {
    if (value.database === 'missing' && value.mirror === 'missing')
      return t('No library data has been saved in this folder yet.')
    if (value.action === 'rewrite_mirror')
      return t(
        'The database is fine, but its saved copy (.grab-library.json) is damaged, missing or out of date. Rewrite the copy from the database.',
      )
    if (value.action === 'rebuild_database')
      return t(
        'The library database is damaged. It can be rebuilt from the saved copy ({count} items). The damaged file is kept next to it, and the most recent change may be missing.',
        { count: value.records },
      )
    if (value.database === 'damaged' && value.mirror !== 'ok')
      return t(
        'The database and its saved copy are both damaged. Nothing was changed. Restore a backup in Backup and restore, or keep the files and ask for help.',
      )
    return t('Library data is healthy: {count} items, and the database matches its saved copy.', {
      count: value.records,
    })
  }

  const action = report?.action
  return (
    <section className="grid gap-2 rounded-xl bg-white/5 p-3" aria-label={t('Library data')}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">{t('Library data')}</h3>
        <Button disabled={busy} onClick={() => void run(checkLibraryData)}>
          <DatabaseZap aria-hidden size={14} />
          {t('Check library data')}
        </Button>
      </div>
      {report && (
        <p className={`text-sm ${action ? 'text-amber-100' : 'text-zinc-300'}`} role="status">
          {summary(report)}
        </p>
      )}
      {action === 'rewrite_mirror' && (
        <Button disabled={busy} onClick={() => void run(() => repairLibraryData('rewrite_mirror'), true)}>
          {t('Rewrite the saved copy')}
        </Button>
      )}
      {action === 'rebuild_database' &&
        (confirming ? (
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => setConfirming(false)}>
              {t('Cancel')}
            </Button>
            <Button
              variant="primary"
              disabled={busy}
              onClick={() => void run(() => repairLibraryData('rebuild_database'), true)}
            >
              {t('Rebuild now')}
            </Button>
          </div>
        ) : (
          <Button variant="primary" disabled={busy} onClick={() => setConfirming(true)}>
            {t('Rebuild the database')}
          </Button>
        ))}
      {error && (
        <p className="text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
