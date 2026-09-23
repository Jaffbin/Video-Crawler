import { ChevronDown, Cookie, Globe2, Gauge, ListVideo, MonitorCog } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import type { ToastFn } from '../../hooks/useToasts'
import type { DownloadOptions } from '../../types/api'
import { CookieSettings } from './CookieSettings'

interface Props {
  options: DownloadOptions
  onChange: (patch: Partial<DownloadOptions>) => void
  onToast: ToastFn
  /** Whether the Playwright package is installed on the backend. */
  playwright: boolean
}

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-zinc-300">
        {icon}
        {title}
      </h3>
      <div className="grid gap-2">{children}</div>
    </section>
  )
}

const Toggle = ({
  checked,
  onChange,
  disabled,
  children,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  children: ReactNode
}) => (
  <label className="toggle-row">
    <input
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
    />
    <span>{children}</span>
  </label>
)

export function AdvancedSettings({ options, onChange, onToast, playwright }: Props) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const number = (v: string) => (v === '' ? 0 : Number(v))

  return (
    <div className="overflow-hidden rounded-2xl border border-white/8 bg-white/[.02]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center justify-between px-4 py-3.5 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <Gauge aria-hidden size={16} className="text-zinc-400" />
          Advanced settings
        </span>
        <ChevronDown
          aria-hidden
          size={17}
          className={`text-zinc-400 transition ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div id={panelId} className="grid gap-5 border-t border-white/8 p-4 lg:grid-cols-2">
          <Section icon={<Cookie aria-hidden size={14} />} title="Authentication">
            <CookieSettings options={options} onChange={onChange} onToast={onToast} />
          </Section>

          <Section icon={<Globe2 aria-hidden size={14} />} title="Network">
            <label className="control">
              <span>Referer (for hotlink protection)</span>
              <input
                className="field"
                placeholder="https://example.com/"
                value={options.referer}
                onChange={(e) => onChange({ referer: e.target.value })}
              />
            </label>
            <label className="control">
              <span>Proxy</span>
              <input
                className="field"
                placeholder="http://127.0.0.1:7890 or socks5://…"
                value={options.proxy}
                onChange={(e) => onChange({ proxy: e.target.value })}
              />
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="control">
                <span>Rate limit</span>
                <input
                  className="field"
                  placeholder="e.g. 2M"
                  value={options.limit_rate}
                  onChange={(e) => onChange({ limit_rate: e.target.value })}
                />
              </label>
              <label className="control">
                <span>Concurrent fragments</span>
                <input
                  className="field"
                  type="number"
                  min={1}
                  max={16}
                  value={options.threads}
                  onChange={(e) => onChange({ threads: number(e.target.value) })}
                />
              </label>
            </div>
            <label className="control">
              <span>Wait between downloads (seconds)</span>
              <input
                className="field"
                type="number"
                min={0}
                max={60}
                step={0.5}
                value={options.sleep}
                onChange={(e) => onChange({ sleep: number(e.target.value) })}
              />
            </label>
          </Section>

          <Section icon={<ListVideo aria-hidden size={14} />} title="Batch">
            <label className="control">
              <span>Playlist range (empty means all)</span>
              <input
                className="field"
                placeholder="e.g. 1-5,8,10-"
                value={options.items}
                onChange={(e) => onChange({ items: e.target.value })}
              />
            </label>
            <Toggle checked={options.no_playlist} onChange={(v) => onChange({ no_playlist: v })}>
              If the link belongs to a playlist, download only this video
            </Toggle>
            <Toggle checked={options.archive} onChange={(v) => onChange({ archive: v })}>
              Skip videos that were already downloaded
            </Toggle>
          </Section>

          <Section icon={<MonitorCog aria-hidden size={14} />} title="Dynamic pages">
            <Toggle
              checked={options.js_render && playwright}
              disabled={!playwright}
              onChange={(v) => onChange({ js_render: v })}
            >
              If no video is found, render the page in a headless browser
            </Toggle>
            <p className="text-xs leading-5 text-zinc-400">
              {playwright
                ? 'Playwright detected. On Windows the built-in Edge is used first, so no extra browser download is needed.'
                : 'Playwright is not installed. Run “pip install playwright” and restart to enable this.'}
            </p>
            <Toggle checked={options.all_sniffed} onChange={(v) => onChange({ all_sniffed: v })}>
              Download every media address found on a page, not just the first that works
            </Toggle>
            <label className="control">
              <span>Longest wait for the page to play (seconds)</span>
              <input
                className="field"
                type="number"
                min={2}
                max={30}
                value={options.js_wait}
                disabled={!playwright}
                onChange={(e) => onChange({ js_wait: number(e.target.value) })}
              />
            </label>
          </Section>
        </div>
      )}
    </div>
  )
}
