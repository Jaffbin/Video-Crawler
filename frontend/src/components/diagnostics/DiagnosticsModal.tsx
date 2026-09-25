import { useState } from 'react'
import { getDoctor } from '../../api/client'
import type { ToastFn } from '../../hooks/useToasts'
import type { ComponentExtras, DoctorResult } from '../../types/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { DoctorList } from './DoctorList'

interface Props {
  open: boolean
  onClose: () => void
  doctor: DoctorResult | null
  onRefresh: () => Promise<void>
  onInstall: (extras: ComponentExtras) => Promise<void>
  installBusy: boolean
  onToast: ToastFn
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function DiagnosticsModal({
  open,
  onClose,
  doctor,
  onRefresh,
  onInstall,
  installBusy,
  onToast,
}: Props) {
  const [loading, setLoading] = useState(false)
  const [netResult, setNetResult] = useState<DoctorResult | null>(null)

  async function recheck() {
    setLoading(true)
    setNetResult(null)
    try {
      await onRefresh()
    } finally {
      setLoading(false)
    }
  }

  async function testNetwork() {
    setLoading(true)
    try {
      setNetResult(await getDoctor(true, true))
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Network test failed', true)
    } finally {
      setLoading(false)
    }
  }

  const checks = netResult?.checks ?? doctor?.checks ?? []
  const report = netResult?.report ?? doctor?.report ?? ''

  return (
    <Modal open={open} onClose={onClose} title="Diagnostics" wide>
      <div className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          <Button onClick={recheck} disabled={loading}>
            Re-check
          </Button>
          <Button onClick={testNetwork} disabled={loading}>
            Test network
          </Button>
          <Button
            variant="ghost"
            disabled={!report}
            onClick={async () =>
              onToast(
                (await copyText(report)) ? 'Report copied. Read it before you share it.' : 'Could not copy',
                !report,
              )
            }
          >
            Copy report
          </Button>
        </div>

        {checks.length === 0 ? (
          <p className="text-sm text-zinc-400">Checking…</p>
        ) : (
          <DoctorList
            checks={checks}
            onCopy={async (fix) =>
              onToast((await copyText(fix)) ? 'Copied' : 'Could not copy')
            }
            onFix={(c) =>
              void onInstall(
                c.action === 'install_components'
                  ? 'default,deno'
                  : 'default',
              )
            }
            busyAction={installBusy ? 'installing' : null}
          />
        )}

        <p className="text-xs text-zinc-500">
          The report hides your home folder and proxy passwords, but it includes your most recent failed links
          and log lines. Read it before you share it.
        </p>
      </div>
    </Modal>
  )
}
