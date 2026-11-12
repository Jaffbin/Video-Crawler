import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n'
import type { DownloadOptions } from '../../types/api'
import {
  BUILTIN_PRESETS,
  outputOptions,
  readPresets,
  writePresets,
  type DownloadPreset,
  type OutputOptions,
} from '../../lib/presets'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'
import { Modal } from '../ui/Modal'

export function DownloadPresets({
  options,
  onApply,
  disabled,
}: {
  options: DownloadOptions
  onApply: (options: OutputOptions) => void
  disabled: boolean
}) {
  const { t } = useI18n()
  const tip = useHelpTip()
  const [custom, setCustom] = useState(readPresets)
  const [selected, setSelected] = useState('')
  const [editing, setEditing] = useState<DownloadPreset | 'new' | null>(null)
  const [deleting, setDeleting] = useState<DownloadPreset | null>(null)
  const [name, setName] = useState(''),
    [error, setError] = useState('')
  useEffect(() => {
    const sync = () => setCustom(readPresets())
    window.addEventListener('storage', sync)
    window.addEventListener('grab-presets-changed', sync)
    return () => {
      window.removeEventListener('storage', sync)
      window.removeEventListener('grab-presets-changed', sync)
    }
  }, [])
  const chosen = custom.find((preset) => preset.id === selected)
  function save() {
    const clean = name.trim(),
      existing = readPresets()
    if (!clean || clean.length > 60 || /[\x00-\x1f]/.test(clean))
      return setError(t('Use a preset name of 1–60 characters.'))
    if (
      existing.some(
        (item) =>
          item.name.toLowerCase() === clean.toLowerCase() &&
          item.id !== (editing === 'new' ? '' : editing?.id),
      )
    )
      return setError(t('A preset with that name already exists.'))
    if (editing === 'new' && existing.length >= 50) return setError(t('You can save up to 50 presets.'))
    try {
      const preset =
        editing === 'new'
          ? { id: crypto.randomUUID().replaceAll('-', ''), name: clean, options: outputOptions(options) }
          : { ...editing!, name: clean }
      writePresets(
        editing === 'new'
          ? [...existing, preset]
          : existing.map((item) => (item.id === preset.id ? preset : item)),
      )
      setSelected(preset.id)
      setEditing(null)
      setError('')
    } catch {
      setError(t('Could not save presets. Check available browser storage.'))
    }
  }
  const matching = [...BUILTIN_PRESETS, ...custom].find(
    (item) => item.id === selected && JSON.stringify(item.options) === JSON.stringify(outputOptions(options)),
  )
  return (
    <div className="grid gap-2 rounded-xl border border-white/[.07] p-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="control min-w-0 flex-1 basis-44">
          <span>{t('Download preset')}</span>
          <select
            className="field"
            value={matching?.id || ''}
            disabled={disabled}
            onChange={(event) => {
              const preset = [...BUILTIN_PRESETS, ...custom].find((item) => item.id === event.target.value)
              if (preset) {
                setSelected(preset.id)
                onApply(preset.options)
              }
            }}
          >
            <option value="">{t('Current settings')}</option>
            <optgroup label={t('Built-in presets')}>
              {BUILTIN_PRESETS.map((item) => (
                <option key={item.id} value={item.id}>
                  {t(item.name)}
                </option>
              ))}
            </optgroup>
            {!!custom.length && (
              <optgroup label={t('My presets')}>
                {custom.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        <Button
          className="!px-2.5 !py-1.5 text-xs"
          disabled={disabled}
          onClick={() => {
            setName('')
            setError('')
            setEditing('new')
          }}
        >
          {t('Save current as preset')}
        </Button>
        {chosen && (
          <>
            <Button
              className="!px-2.5 !py-1.5 text-xs"
              disabled={disabled}
              onClick={() => {
                setName(chosen.name)
                setError('')
                setEditing(chosen)
              }}
            >
              {t('Rename preset')}
            </Button>
            <Button
              className="!px-2.5 !py-1.5 text-xs"
              disabled={disabled}
              onClick={() => {
                setError('')
                setDeleting(chosen)
              }}
            >
              {t('Delete preset')}
            </Button>
          </>
        )}
        <span className="ml-auto self-center">
          <HelpButton tip={tip} about={t('Download preset')} />
        </span>
      </div>
      <HelpNote tip={tip}>
        {t('Presets change output settings only. You can adjust them before downloading.')}
      </HelpNote>
      <Modal
        open={!!editing}
        title={t(editing === 'new' ? 'Save current as preset' : 'Rename preset')}
        onClose={() => setEditing(null)}
      >
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            save()
          }}
        >
          <label className="control">
            <span>{t('Preset name')}</span>
            <input
              className="field"
              value={name}
              maxLength={60}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="text-red-300">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" variant="primary">
              {t('Save')}
            </Button>
            <Button onClick={() => setEditing(null)}>{t('Cancel')}</Button>
          </div>
        </form>
      </Modal>
      <Modal open={!!deleting} title={t('Delete preset')} onClose={() => setDeleting(null)}>
        <p className="mb-4 break-words">
          {t('Delete preset “{name}”? Downloaded files are kept.', { name: deleting?.name || '' })}
        </p>
        {error && (
          <p role="alert" className="mb-3 text-red-300">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            onClick={() => {
              try {
                writePresets(readPresets().filter((item) => item.id !== deleting?.id))
                setSelected('')
                setDeleting(null)
                setError('')
              } catch {
                setError(t('Could not save presets. Check available browser storage.'))
              }
            }}
          >
            {t('Delete preset')}
          </Button>
          <Button onClick={() => setDeleting(null)}>{t('Cancel')}</Button>
        </div>
      </Modal>
    </div>
  )
}
