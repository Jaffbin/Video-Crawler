import { useEffect, useRef, useState } from 'react'
import { checkYtdlp, getUpdateStatus, startYtdlpUpdate } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { ComponentExtras, YtdlpCheck } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'

interface Props {
  open: boolean
  onClose: () => void
  onRestart: () => void
  onToast: ToastFn
  /** So the header dot clears once the check is known to be current. */
  onChecked: (check: YtdlpCheck) => void
}

type Phase = 'idle' | 'checking' | 'installing' | 'needs-restart' | 'done' | 'error'

export function UpdateModal({ open, onClose, onRestart, onToast, onChecked }: Props) {
  const [check, setCheck] = useState<YtdlpCheck | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState('')
  const poller = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (open) void refresh(true)
    return () => window.clearTimeout(poller.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function refresh(force: boolean) {
    setPhase('checking')
    try {
      const c = await checkYtdlp(force)
      setCheck(c)
      onChecked(c)
      setPhase(c.needs_restart ? 'needs-restart' : 'idle')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not check for updates')
      setPhase('error')
    }
  }

  async function install(extras: ComponentExtras) {
    setPhase('installing')
    setLog([])
    setError('')
    try {
      await startYtdlpUpdate(extras)
    } catch (e) {
      setPhase('error')
      setError(e instanceof Error ? e.message : 'Could not start the update')
      return
    }
    poll()
  }

  function poll() {
    window.clearTimeout(poller.current)
    poller.current = window.setTimeout(async () => {
      let status
      try {
        status = await getUpdateStatus()
      } catch {
        poll()
        return
      }
      setLog(status.lines)
      if (status.status === 'running') {
        poll()
        return
      }
      if (status.status === 'error') {
        setPhase('error')
        setError(status.error || 'Update failed')
        return
      }
      if (status.extras.includes('deno')) {
        setPhase('needs-restart')
      } else {
        await refresh(true)
      }
    }, 800)
  }

  return (
    <Modal open={open} onClose={onClose} title="yt-dlp updates">
      <div className="grid gap-4 text-sm">
        {phase === 'checking' && <p className="text-zinc-400">Checking…</p>}

        {check && phase !== 'checking' && phase !== 'installing' && (
          <div className="rounded-xl bg-white/[.03] p-3">
            <p>
              Running <span className="font-mono">{check.running}</span>
              {check.installed !== check.running && (
                <>
                  {' '}
                  (installed <span className="font-mono">{check.installed}</span>, restart to use it)
                </>
              )}
            </p>
            {check.latest && <p className="mt-1 text-zinc-400">Latest on PyPI: {check.latest}</p>}
          </div>
        )}

        {phase === 'needs-restart' && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-emerald-500/[.08] p-3 text-emerald-200">
            <span>Update installed. Restart the service to use it.</span>
            <Button variant="primary" onClick={onRestart}>
              Restart service
            </Button>
          </div>
        )}

        {phase === 'error' && (
          <p role="alert" className="rounded-xl bg-red-500/[.08] p-3 text-red-200">
            {error}
          </p>
        )}

        {(phase === 'installing' || log.length > 0) && (
          <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-black/40 p-3 font-mono text-xs text-zinc-300">
            {log.join('\n') || 'Starting…'}
          </pre>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => refresh(true)} disabled={phase === 'checking' || phase === 'installing'}>
            Check again
          </Button>
          <Button
            variant="primary"
            disabled={phase === 'installing' || phase === 'checking'}
            onClick={() => void install(check?.newer ? 'default' : 'default,deno')}
          >
            {check?.newer ? 'Update yt-dlp' : 'Install YouTube components'}
          </Button>
          <Button
            variant="ghost"
            disabled={phase === 'installing'}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText('pip install -U "yt-dlp[default,deno]"')
                onToast('Command copied')
              } catch {
                onToast('Could not copy', true)
              }
            }}
          >
            Copy command
          </Button>
        </div>
      </div>
    </Modal>
  )
}
