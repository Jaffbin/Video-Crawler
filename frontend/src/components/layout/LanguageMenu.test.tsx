import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { I18nProvider, useI18n } from '../../i18n'
import { LanguageMenu } from './LanguageMenu'

function Appearance() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const { t } = useI18n()
  return (
    <>
      <button onClick={(event) => setAnchor(event.currentTarget)}>{t('Language')}</button>
      {anchor && <LanguageMenu anchor={anchor} onClose={() => setAnchor(null)} />}
    </>
  )
}

it('switches and remembers a language through its independent menu', async () => {
  localStorage.setItem('grab-locale', 'en')
  const user = userEvent.setup()
  const first = render(
    <I18nProvider>
      <Appearance />
    </I18nProvider>,
  )
  await user.click(screen.getByRole('button', { name: 'Language' }))
  expect(screen.getByRole('button', { name: 'English' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: '简体中文' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(localStorage.getItem('grab-locale')).toBe('zh-CN')
  expect(document.documentElement).toHaveAttribute('lang', 'zh-CN')
  expect(screen.getByRole('button', { name: '语言' })).toHaveFocus()
  first.unmount()
  render(
    <I18nProvider>
      <Appearance />
    </I18nProvider>,
  )
  await user.click(screen.getByRole('button', { name: '语言' }))
  expect(screen.getByRole('button', { name: '简体中文' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'English' }))
  expect(localStorage.getItem('grab-locale')).toBe('en')
})

it('dismisses without changing language and restores keyboard focus', async () => {
  localStorage.setItem('grab-locale', 'en')
  const user = userEvent.setup()
  render(
    <I18nProvider>
      <Appearance />
    </I18nProvider>,
  )
  const trigger = screen.getByRole('button', { name: 'Language' })
  await user.click(trigger)
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(localStorage.getItem('grab-locale')).toBe('en')
})
