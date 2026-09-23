import { useEffect, useRef, useState } from 'react'
import { deleteCookies, getCookies, uploadCookies } from '../../api/client'
import { BROWSERS } from '../../lib/options'
import type { ToastFn } from '../../hooks/useToasts'
import type { CookieStatus, DownloadOptions } from '../../types/api'

interface Props {
  options: DownloadOptions
  onChange: (patch: Partial<DownloadOptions>) => void
  onToast: ToastFn
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

export function describeCookies(c: CookieStatus): string {
  if (!c.present) return 'No cookies.txt uploaded.'
  const bits = [`${plural(c.cookies ?? 0, 'cookie')} for ${plural(c.domain_count ?? 0, 'site')}`]
  if (c.expired) bits.push(`${c.expired} already expired`)
  if (c.has_youtube) bits.push(c.youtube_login ? 'YouTube sign-in found' : 'no YouTube sign-in cookies')
  if (c.has_bilibili) bits.push(c.bilibili_login ? 'Bilibili sign-in found' : 'no Bilibili sign-in cookie')
  return `${bits.join('; ')}.`
}

export function CookieSettings({ options, onChange, onToast }: Props) {
  const [status, setStatus] = useState<CookieStatus>({ present: false })
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getCookies()
      .then((s) => {
        setStatus(s)
        // A remembered "use the uploaded file" choice is meaningless if the file is gone.
        if (!s.present && options.use_cookies_file) onChange({ use_cookies_file: false })
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selected = options.use_cookies_file ? 'file' : options.cookies_from_browser

  async function upload(file: File) {
    if (file.size > 3_000_000)
      return onToast('That file is larger than 3 MB, so it is probably not a cookies.txt.', true)
    try {
      setStatus(await uploadCookies(await file.text()))
      onChange({ use_cookies_file: true, cookies_from_browser: '' })
      onToast('cookies.txt uploaded')
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Upload failed', true)
    }
  }

  async function remove() {
    try {
      setStatus(await deleteCookies())
      onChange({ use_cookies_file: false })
      onToast('cookies.txt removed')
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Could not remove the file', true)
    }
  }

  return (
    <div className="grid gap-2">
      <label className="control">
        <span>Cookies (for logged-in or member-only videos)</span>
        <select
          className="field"
          value={selected}
          onChange={(e) => {
            const v = e.target.value
            onChange(
              v === 'file'
                ? { use_cookies_file: true, cookies_from_browser: '' }
                : { use_cookies_file: false, cookies_from_browser: v },
            )
          }}
        >
          <option value="">No cookies</option>
          <option value="file" disabled={!status.present}>
            Uploaded cookies.txt
          </option>
          <optgroup label="Read from a browser">
            {BROWSERS.map((b) => (
              <option key={b} value={b}>
                {b[0].toUpperCase() + b.slice(1)}
              </option>
            ))}
          </optgroup>
        </select>
      </label>

      <div className="rounded-xl bg-white/[.035] px-3 py-2 text-xs text-zinc-300">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>{describeCookies(status)}</span>
          <span className="flex gap-2">
            <button
              type="button"
              className="rounded-lg bg-white/[.06] px-2.5 py-1.5 hover:bg-white/[.1]"
              onClick={() => fileInput.current?.click()}
            >
              Upload cookies.txt
            </button>
            {status.present && (
              <button
                type="button"
                className="rounded-lg px-2.5 py-1.5 text-red-300 hover:bg-white/[.06]"
                onClick={remove}
              >
                Remove
              </button>
            )}
          </span>
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".txt,text/plain"
          hidden
          aria-label="cookies.txt file"
          onChange={(e) => {
            const f = e.target.files?.[0]
            e.target.value = ''
            if (f) void upload(f)
          }}
        />
        <p className="mt-2 leading-5 text-zinc-400">
          Reading cookies straight from Chrome or Edge can fail on Windows while the browser is open; an
          exported cookies.txt avoids that. YouTube rotates account cookies, so export from a private window
          and do not reuse that window afterwards (
          <a
            className="underline"
            href="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
            target="_blank"
            rel="noreferrer"
          >
            how to export
          </a>
          ). The file is stored outside your download folder and every run works on its own copy.
        </p>
      </div>
    </div>
  )
}
