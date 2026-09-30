import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { I18nProvider, LOCALES, useI18n } from './i18n'

function Example() {
  const { locale, setLocale, t } = useI18n()
  return (
    <>
      <span>{t('New download')}</span>
      <span>{t('Preview filters')}</span>
      <span>{t('error.title.network')}</span>
      <select
        aria-label="language"
        value={locale}
        onChange={(event) => setLocale(event.target.value as typeof locale)}
      >
        {LOCALES.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </>
  )
}

afterEach(() => localStorage.clear())

it('switches language and persists the choice', async () => {
  render(
    <I18nProvider>
      <Example />
    </I18nProvider>,
  )
  await userEvent.selectOptions(screen.getByLabelText('language'), 'zh-CN')
  expect(screen.getByText('新建下载')).toBeInTheDocument()
  expect(localStorage.getItem('grab-locale')).toBe('zh-CN')
  expect(document.documentElement.lang).toBe('zh-CN')
  expect(screen.getByText('预览过滤结果')).toBeInTheDocument()
  expect(screen.getByText('无法连接网站。')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('language'), 'zh-TW')
  expect(screen.getByText('預覽篩選結果')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('language'), 'ja')
  expect(screen.getByText('フィルターをプレビュー')).toBeInTheDocument()
})
