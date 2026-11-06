import { afterEach, expect, it, vi } from 'vitest'
import { importLibraryFile, resetTokenCache } from './client'

class Request {
  static latest: Request
  upload: { onprogress?: (event: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
  headers: Record<string, string> = {}
  status = 200
  responseText = '{"path":"imports/clip.mp4","duplicate":false}'
  onload?: () => void
  onerror?: () => void
  onabort?: () => void
  method = ''
  url = ''
  body?: File
  constructor() {
    Request.latest = this
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  send(file: File) {
    this.body = file
  }
  abort() {
    this.onabort?.()
  }
}
afterEach(() => {
  vi.unstubAllGlobals()
  document.querySelector('meta[name="grab-token"]')?.remove()
  resetTokenCache()
})
it('streams raw file bytes with authentication, encoded names and progress', async () => {
  document.head.insertAdjacentHTML('beforeend', '<meta name="grab-token" content="fixture-token">')
  resetTokenCache()
  vi.stubGlobal('XMLHttpRequest', Request)
  const file = new File(['video bytes'], '教程 & audio.mp4'),
    controller = new AbortController(),
    progress = vi.fn()
  const pending = importLibraryFile(file, controller.signal, progress)
  const request = Request.latest
  expect(request.method).toBe('POST')
  expect(request.url).toBe('/api/library/import?name=' + encodeURIComponent(file.name))
  expect(request.headers).toEqual({ 'X-Token': 'fixture-token', 'Content-Type': 'application/octet-stream' })
  expect(request.body).toBe(file)
  request.upload.onprogress?.({ lengthComputable: true, loaded: 3, total: 10 })
  expect(progress).toHaveBeenCalledWith(30)
  request.onload?.()
  await expect(pending).resolves.toEqual({ path: 'imports/clip.mp4', duplicate: false })
})
it('cancels the owned request and reports server conflicts', async () => {
  vi.stubGlobal('XMLHttpRequest', Request)
  const controller = new AbortController()
  const pending = importLibraryFile(new File(['bytes'], 'clip.mp4'), controller.signal, vi.fn())
  controller.abort()
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  const conflict = importLibraryFile(new File(['bytes'], 'clip.mp4'), new AbortController().signal, vi.fn())
  Request.latest.status = 409
  Request.latest.responseText = '{"error":"A file already exists"}'
  Request.latest.onload?.()
  await expect(conflict).rejects.toThrow('A file already exists')
})
