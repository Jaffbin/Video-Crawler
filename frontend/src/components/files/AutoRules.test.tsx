import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { resetTokenCache } from '../../api/client'
import type { AutoRule, FileItem } from '../../types/api'
import { AutoRules } from './AutoRules'

afterEach(() => vi.unstubAllGlobals())

const MUSIC = 'a'.repeat(32)
const files = [
  { name: 'song.mp3', path: 'song.mp3', size: 1, mtime: 1, source: 'www.bilibili.com' },
  { name: 'clip.mp4', path: 'clip.mp4', size: 1, mtime: 1, source: 'local' },
] as FileItem[]

const existing: AutoRule = {
  id: 'b'.repeat(32),
  name: 'Bili',
  enabled: true,
  conditions: { source: 'bilibili.com', kind: 'video' },
  actions: { tags: ['B站'], collections: [MUSIC], favorite: true },
}

function serve(initial: AutoRule[]) {
  let rules = initial
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body))
        posts.push(body)
        if (body.rule?.conditions?.source === 'bad')
          return new Response(JSON.stringify({ error: 'Enter a site such as bilibili.com.' }), {
            status: 400,
          })
        if (body.action === 'create') rules = [...rules, { id: 'c'.repeat(32), ...body.rule }]
        if (body.action === 'update')
          rules = rules.map((rule) => (rule.id === body.id ? { id: body.id, ...body.rule } : rule))
        if (body.action === 'delete') rules = rules.filter((rule) => rule.id !== body.id)
        return new Response(JSON.stringify({ id: body.id, auto_rules: rules }))
      }
      return new Response(JSON.stringify({ auto_rules: rules }))
    }),
  )
  return posts
}

function renderRules() {
  return render(<AutoRules files={files} collections={[{ id: MUSIC, name: 'Music' }]} onToast={vi.fn()} />)
}

it('describes each rule in plain words', async () => {
  resetTokenCache()
  serve([existing])
  renderRules()
  expect(
    await screen.findByText('When bilibili.com, Videos, add tags B站, collection Music, favorite.'),
  ).toBeInTheDocument()
})

it('creates a rule from a site, tags, a collection and favorite', async () => {
  resetTokenCache()
  const posts = serve([])
  const user = userEvent.setup()
  renderRules()
  expect(await screen.findByText('Create your first auto rule below.')).toBeInTheDocument()
  const create = screen.getByRole('button', { name: 'Create auto rule' })
  expect(create).toBeDisabled()
  await user.type(screen.getByLabelText('Rule name'), 'Music from Bili')
  await user.type(screen.getByLabelText('Source site'), 'bilibili.com')
  await user.selectOptions(screen.getByLabelText('Media type'), 'audio')
  expect(create).toBeDisabled() // conditions alone are not enough
  await user.type(screen.getByLabelText('Add tags (separate with commas)'), 'B站， music ,')
  await user.click(screen.getByLabelText('Music'))
  await user.click(screen.getByLabelText('Mark as favorite'))
  await user.click(create)
  await waitFor(() =>
    expect(posts.at(-1)).toEqual({
      action: 'create',
      rule: {
        name: 'Music from Bili',
        enabled: true,
        conditions: { source: 'bilibili.com', kind: 'audio' },
        actions: { tags: ['B站', 'music'], collections: [MUSIC], favorite: true },
      },
    }),
  )
  expect(await screen.findByText('Music from Bili')).toBeInTheDocument()
  expect(screen.getByLabelText('Rule name')).toHaveValue('')
})

it('turns a rule off, edits it and deletes it after confirmation', async () => {
  resetTokenCache()
  const posts = serve([existing])
  const user = userEvent.setup()
  renderRules()
  await user.click(await screen.findByRole('button', { name: 'Turn off auto rule Bili' }))
  await waitFor(() => expect(posts.at(-1)).toMatchObject({ action: 'update', rule: { enabled: false } }))
  expect(await screen.findByText('(off)')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Edit auto rule Bili' }))
  expect(screen.getByLabelText('Source site')).toHaveValue('bilibili.com')
  expect(screen.getByLabelText('Music')).toBeChecked()
  await user.clear(screen.getByLabelText('Rule name'))
  await user.type(screen.getByLabelText('Rule name'), 'Bilibili')
  await user.click(screen.getByRole('button', { name: 'Save auto rule' }))
  await waitFor(() => expect(posts.at(-1)).toMatchObject({ action: 'update', rule: { name: 'Bilibili' } }))

  await user.click(await screen.findByRole('button', { name: 'Delete auto rule Bilibili' }))
  expect(screen.getByText(/already added are kept/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Delete auto rule' }))
  await waitFor(() => expect(posts.at(-1)).toEqual({ action: 'delete', id: existing.id }))
  expect(await screen.findByText('Create your first auto rule below.')).toBeInTheDocument()
})

it('shows the reason when the app rejects a rule and keeps the form', async () => {
  resetTokenCache()
  serve([])
  const user = userEvent.setup()
  renderRules()
  await user.type(await screen.findByLabelText('Rule name'), 'Broken')
  await user.type(screen.getByLabelText('Source site'), 'bad')
  await user.click(screen.getByLabelText('Mark as favorite'))
  await user.click(screen.getByRole('button', { name: 'Create auto rule' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Enter a site such as bilibili.com.')
  expect(screen.getByLabelText('Rule name')).toHaveValue('Broken')
})
