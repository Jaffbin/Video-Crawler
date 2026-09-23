import { useCallback, useEffect, useMemo, useState } from 'react'
import { getUpdateStatus, openFolder, startYtdlpUpdate } from './api/client'
import { Banners } from './components/layout/Banners'
import { Header, type NotificationMode } from './components/layout/Header'
import { RestartOverlay } from './components/layout/RestartOverlay'
import { NewDownloadPanel } from './components/download/NewDownloadPanel'
import { QueuePanel } from './components/queue/QueuePanel'
import { FileGallery } from './components/files/FileGallery'
import { DiagnosticsModal } from './components/diagnostics/DiagnosticsModal'
import { UpdateModal } from './components/diagnostics/UpdateModal'
import { Toasts } from './components/ui/Toast'
import { useStatePolling } from './hooks/useStatePolling'
import { useCompletionNotifier } from './hooks/useCompletionNotifier'
import { useEnvironment } from './hooks/useEnvironment'
import { useRestart } from './hooks/useRestart'
import { useToasts } from './hooks/useToasts'
import type { ComponentExtras, YtdlpCheck } from './types/api'

function useNotificationMode(serverNotifies: boolean): [NotificationMode, () => void] {
  const supported = typeof Notification !== 'undefined'
  const [permission, setPermission] = useState(supported ? Notification.permission : 'default')

  const request = useCallback(() => {
    if (!supported) return
    void Notification.requestPermission().then(setPermission)
  }, [supported])

  if (serverNotifies) return ['server', request]
  if (!supported) return ['unsupported', request]
  return [permission as NotificationMode, request]
}

export default function App() {
  const { state, online, refresh, refreshFiles } = useStatePolling()
  const { toasts, push: toast, remove } = useToasts()
  const environment = useEnvironment()
  const { restarting, restartService } = useRestart((m) => toast(m, true))
  const [notifyMode, requestNotify] = useNotificationMode(!!state.desktop_notifications)
  const [doctorOpen, setDoctorOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [installBusy, setInstallBusy] = useState(false)
  const [ytdlpCheck, setYtdlpCheck] = useState<YtdlpCheck | null>(null)

  useCompletionNotifier(state.jobs, {
    serverNotifies: !!state.desktop_notifications,
    onAnnounce: (m, bad) => toast(m, bad),
  })

  const updateAttention = !!ytdlpCheck && (ytdlpCheck.newer || ytdlpCheck.needs_restart)

  async function install(extras: ComponentExtras) {
    setInstallBusy(true)
    try {
      await startYtdlpUpdate(extras)
      // Poll to completion so the Diagnostics panel can show the log; the Update modal has its own poller
      // for when the user opens *that* dialog instead, so this just waits quietly.
      for (;;) {
        const s = await getUpdateStatus()
        if (s.status !== 'running') break
        await new Promise((r) => setTimeout(r, 900))
      }
      await environment.refresh()
      toast('Components installed. Open Update to restart the service.')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Install failed', true)
    } finally {
      setInstallBusy(false)
    }
  }

  const jobs = useMemo(() => state.jobs, [state.jobs])

  useEffect(() => {
    if (online) return
    const id = window.setInterval(() => void refresh(), 2000)
    return () => window.clearInterval(id)
  }, [online, refresh])

  return (
    <div className="min-h-screen pb-16">
      <Header
        version={state.version}
        online={online}
        windowMode={!!state.window}
        updateAttention={updateAttention}
        environmentAttention={environment.showBanner}
        notification={notifyMode}
        onDoctor={() => setDoctorOpen(true)}
        onUpdate={() => setUpdateOpen(true)}
        onOpenFolder={() =>
          openFolder().catch((e) => toast(e instanceof Error ? e.message : 'Could not open the folder', true))
        }
        onNotify={requestNotify}
      />
      <Banners
        online={online}
        ffmpeg={state.ffmpeg}
        youtubeIssues={environment.issues}
        showYoutubeIssues={environment.showBanner}
        onOpenDiagnostics={() => setDoctorOpen(true)}
        onDismissYoutubeIssues={environment.dismiss}
      />

      <main className="mx-auto grid max-w-[1500px] gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[420px_1fr]">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <NewDownloadPanel playwright={state.playwright} onToast={toast} onAdded={refresh} />
        </div>
        <div className="grid gap-5">
          <QueuePanel jobs={jobs} windowMode={!!state.window} onChanged={refresh} onToast={toast} />
          <FileGallery
            files={state.files ?? []}
            windowMode={!!state.window}
            onRefresh={refreshFiles}
            onToast={toast}
          />
        </div>
      </main>

      <DiagnosticsModal
        open={doctorOpen}
        onClose={() => setDoctorOpen(false)}
        doctor={environment.doctor}
        onRefresh={environment.refresh}
        onInstall={install}
        installBusy={installBusy}
        onToast={toast}
      />
      <UpdateModal
        open={updateOpen}
        onClose={() => setUpdateOpen(false)}
        onRestart={() => {
          setUpdateOpen(false)
          void restartService()
        }}
        onToast={toast}
        onChecked={setYtdlpCheck}
      />

      {restarting && <RestartOverlay windowMode={!!state.window} />}
      <Toasts items={toasts} onRemove={remove} />
    </div>
  )
}
