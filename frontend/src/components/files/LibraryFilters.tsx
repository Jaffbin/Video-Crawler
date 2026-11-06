import type { LibraryCollection, SmartCollection } from '../../types/api'
import { smartName } from '../../lib/smartCollections'
import type { LibrarySort } from '../../lib/library'
import { useI18n } from '../../i18n'

export interface LibraryFilterValues {
  kind: string
  source: string
  format: string
  collection: string
  smart: string
  sort: LibrarySort
}

export function LibraryFilters({
  values,
  sources,
  formats,
  collections,
  smartCollections,
  onChange,
}: {
  values: LibraryFilterValues
  sources: string[]
  formats: string[]
  collections: LibraryCollection[]
  smartCollections: SmartCollection[]
  onChange: (change: Partial<LibraryFilterValues>) => void
}) {
  const { t } = useI18n()
  return (
    <div className="grid gap-3">
      <label className="control">
        <span>{t('Media type')}</span>
        <select className="field" value={values.kind} onChange={(e) => onChange({ kind: e.target.value })}>
          <option value="">{t('All media')}</option>
          <option value="video">{t('Videos')}</option>
          <option value="audio">{t('Audio')}</option>
          <option value="image">{t('Images')}</option>
        </select>
      </label>
      <label className="control">
        <span>{t('Source site')}</span>
        <select
          className="field"
          value={values.source}
          onChange={(e) => onChange({ source: e.target.value })}
        >
          <option value="">{t('All sources')}</option>
          {sources.map((site) => (
            <option key={site} value={site}>
              {site === 'unknown' ? t('Unknown source') : site === 'local' ? t('Local file') : site}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        <span>{t('Format')}</span>
        <select
          className="field"
          value={values.format}
          onChange={(e) => onChange({ format: e.target.value })}
        >
          <option value="">{t('All formats')}</option>
          {formats.map((extension) => (
            <option key={extension} value={extension}>
              {extension.slice(1).toUpperCase()}
            </option>
          ))}
        </select>
      </label>
      <label className="control">
        <span>{t('Collection')}</span>
        <select
          className="field"
          value={values.smart ? `smart:${values.smart}` : values.collection}
          onChange={(e) =>
            onChange(
              e.target.value.startsWith('smart:')
                ? { collection: '', smart: e.target.value.slice(6) }
                : { collection: e.target.value, smart: '' },
            )
          }
        >
          <option value="">{t('All collections')}</option>
          <optgroup label={t('Manual collections')}>
            {collections.map((collection) => (
              <option key={collection.id} value={collection.id}>
                {collection.name}
              </option>
            ))}
          </optgroup>
          <optgroup label={t('Built-in smart collections')}>
            {smartCollections
              .filter((item) => item.builtin)
              .map((item) => (
                <option key={item.id} value={`smart:${item.id}`}>
                  {smartName(item, t)}
                </option>
              ))}
          </optgroup>
          {smartCollections.some((item) => !item.builtin) && (
            <optgroup label={t('My smart collections')}>
              {smartCollections
                .filter((item) => !item.builtin)
                .map((item) => (
                  <option key={item.id} value={`smart:${item.id}`}>
                    {item.name}
                  </option>
                ))}
            </optgroup>
          )}
        </select>
      </label>
      <label className="control">
        <span>{t('Sort files')}</span>
        <select
          className="field"
          value={values.sort}
          onChange={(e) => onChange({ sort: e.target.value as LibrarySort })}
        >
          <option value="newest">{t('Newest first')}</option>
          <option value="oldest">{t('Oldest first')}</option>
          <option value="name">{t('Name')}</option>
          <option value="largest">{t('Largest first')}</option>
        </select>
      </label>
    </div>
  )
}
