import { Clock } from 'lucide-react'
import { useState } from 'react'
import { saveSchedule } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import { useI18n } from '../../i18n'
import type { ScheduleView } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

const NIGHT = { start: '23:00', end: '07:00' }
const DAY = { start: '09:00', end: '18:00' }

function clock(seconds: number) {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Notice above the queue while the schedule keeps tasks waiting or limits new downloads. */
export function ScheduleNotice({ schedule }: { schedule?: ScheduleView }) {
  const { t } = useI18n()
  if (!schedule?.enabled) return null
  if (schedule.holding && schedule.next_start)
    return (
      <p role="status" className="rounded-xl bg-sky-500/[.08] px-3 py-2 text-sm text-sky-100">
        {t('Queued downloads wait for the download window and start at {time}.', {
          time: clock(schedule.next_start),
        })}
      </p>
    )
  if (schedule.limit_active)
    return (
      <p role="status" className="rounded-xl bg-white/[.04] px-3 py-2 text-sm text-zinc-300">
        {t('Busy hours: new downloads are limited to {rate}/s.', { rate: schedule.limit_active })}
      </p>
    )
  return null
}

/**
 * Edit when queued downloads may start and when new downloads get a speed limit. Only the start
 * of a task is scheduled; running downloads continue unchanged.
 */
export function ScheduleControl({
  schedule,
  onChanged,
  onToast,
}: {
  schedule?: ScheduleView
  onChanged: () => void
  onToast: ToastFn
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [useWindow, setUseWindow] = useState(true)
  const [hours, setHours] = useState(NIGHT)
  const [useLimit, setUseLimit] = useState(false)
  const [limit, setLimit] = useState({ ...DAY, rate: '2M' })

  function openDialog() {
    setEnabled(schedule?.enabled ?? false)
    setUseWindow(schedule ? !!schedule.window || !schedule.limit : true)
    setHours(schedule?.window ?? NIGHT)
    setUseLimit(!!schedule?.limit)
    setLimit(schedule?.limit ?? { ...DAY, rate: '2M' })
    setError('')
    setOpen(true)
  }

  async function save() {
    setBusy(true)
    setError('')
    try {
      await saveSchedule({
        enabled,
        window: useWindow ? hours : null,
        limit: useLimit ? limit : null,
      })
      setOpen(false)
      onChanged()
      onToast(t('Download schedule saved'))
    } catch (reason) {
      setError(t(reason instanceof Error ? reason.message : 'That did not work'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button onClick={openDialog}>
        <Clock aria-hidden size={14} />
        {t('Download schedule')}
        {schedule?.enabled && <span className="text-sky-300">{t('On')}</span>}
      </Button>
      <Modal
        open={open}
        title={t('Download schedule')}
        onClose={() => {
          if (!busy) setOpen(false)
        }}
      >
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <p className="text-sm text-zinc-400">
            {t(
              'The schedule decides when queued downloads start. Downloads that are already running continue unchanged.',
            )}
          </p>
          <label className="toggle-row">
            <input
              type="checkbox"
              checked={enabled}
              disabled={busy}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span>{t('Use a download schedule')}</span>
          </label>
          <fieldset disabled={busy || !enabled} className="grid gap-3 disabled:opacity-50">
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={useWindow}
                onChange={(event) => setUseWindow(event.target.checked)}
              />
              <span>{t('Only start downloads during these hours')}</span>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="control">
                <span>{t('From')}</span>
                <input
                  className="field"
                  type="time"
                  required
                  disabled={!useWindow}
                  value={hours.start}
                  onChange={(event) => setHours({ ...hours, start: event.target.value })}
                />
              </label>
              <label className="control">
                <span>{t('Until')}</span>
                <input
                  className="field"
                  type="time"
                  required
                  disabled={!useWindow}
                  value={hours.end}
                  onChange={(event) => setHours({ ...hours, end: event.target.value })}
                />
              </label>
            </div>
          </fieldset>
          <fieldset disabled={busy || !enabled} className="grid gap-3 disabled:opacity-50">
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={useLimit}
                onChange={(event) => setUseLimit(event.target.checked)}
              />
              <span>{t('Limit speed during busy hours')}</span>
            </label>
            <div className="grid grid-cols-3 gap-3">
              <label className="control">
                <span>{t('Busy from')}</span>
                <input
                  className="field"
                  type="time"
                  required
                  disabled={!useLimit}
                  value={limit.start}
                  onChange={(event) => setLimit({ ...limit, start: event.target.value })}
                />
              </label>
              <label className="control">
                <span>{t('Busy until')}</span>
                <input
                  className="field"
                  type="time"
                  required
                  disabled={!useLimit}
                  value={limit.end}
                  onChange={(event) => setLimit({ ...limit, end: event.target.value })}
                />
              </label>
              <label className="control">
                <span>{t('Speed limit')}</span>
                <input
                  className="field"
                  placeholder="2M"
                  required
                  disabled={!useLimit}
                  value={limit.rate}
                  onChange={(event) => setLimit({ ...limit, rate: event.target.value })}
                />
              </label>
            </div>
            <p className="text-xs text-zinc-400">
              {t(
                'Applies to downloads that start during busy hours and have no speed limit of their own. Examples: 2M, 500K.',
              )}
            </p>
          </fieldset>
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" type="submit" disabled={busy}>
              {t('Save schedule')}
            </Button>
            <Button disabled={busy} onClick={() => setOpen(false)}>
              {t('Cancel')}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
