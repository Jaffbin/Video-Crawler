import { useCallback, useMemo, useState } from 'react'
import { loadOptions, saveOptions } from './lib/options'
import { getUpdateStatus, openFolder, startYtdlpUpdate } from './api/client'
import { Banners } from './components/layout/Banners'
import { Header, type NotificationMode } from './components/layout/Header'
import { Sidebar } from './components/layout/Sidebar'
import { RestartOverlay } from './components/layout/RestartOverlay'
import { NewDownloadPanel } from './components/download/NewDownloadPanel'
import { QueuePanel } from './components/queue/QueuePanel'
import { SubscriptionsPanel } from './components/subscriptions/SubscriptionsPanel'
import { FileGallery } from './components/files/FileGallery'
import { DiagnosticsModal } from './components/diagnostics/DiagnosticsModal'
import { UpdateModal } from './components/diagnostics/UpdateModal'
import { Toasts } from './components/ui/Toast'
import { useStatePolling } from './hooks/useStatePolling'
import { useCompletionNotifier } from './hooks/useCompletionNotifier'
import { useEnvironment } from './hooks/useEnvironment'
import { useRestart } from './hooks/useRestart'
import { useSubscriptions } from './hooks/useSubscriptions'
import { useToasts } from './hooks/useToasts'
import { useNavigation, type AppView } from './hooks/useNavigation'
import type { ComponentExtras, DownloadOptions, YtdlpCheck } from './types/api'

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
  const { subscriptions, intervalSeconds, refresh: refreshSubs } = useSubscriptions()
  // One copy of the download settings, shared by "New download" and the subscription form.
  const [options, setOptions] = useState<DownloadOptions>(loadOptions)
  const patchOptions = useCallback((change: Partial<DownloadOptions>) => {
    setOptions((current) => {
      const next = { ...current, ...change }
      saveOptions(next)
      return next
    })
  }, [])
  const { toasts, push: toast, remove } = useToasts()
  const environment = useEnvironment()
  const { restarting, restartService } = useRestart((m) => toast(m, true))
  const [notifyMode, requestNotify] = useNotificationMode(!!state.desktop_notifications)
  const [doctorOpen, setDoctorOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [installBusy, setInstallBusy] = useState(false)
  const [ytdlpCheck, setYtdlpCheck] = useState<YtdlpCheck | null>(null)
  const { view, navigate } = useNavigation()

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
  const activeJobs = jobs.filter((job) => job.status === 'queued' || job.status === 'running').length
  const failedJobs = jobs.filter((job) => job.status === 'error' || job.status === 'canceled').length
  const viewCopy: Record<AppView, { title: string; description: string }> = {
    new: { title: 'New download', description: 'Add one or more video, playlist, MP4 or M3U8 links.' },
    queue: { title: 'Queue', description: 'Track active jobs and review completed or failed downloads.' },
    'auto-download': {
      title: 'Auto-download',
      description: 'Watch channels and playlists for newly published videos.',
    },
    library: { title: 'Library', description: 'Browse files saved in your download folder.' },
  }

  const openFolderFromUi = () =>
    openFolder().catch((e) => toast(e instanceof Error ? e.message : 'Could not open the folder', true))

  return (
    <div className="min-h-screen pb-24 md:pb-0 md:pl-60">
      <Sidebar
        view={view}
        version={state.version}
        online={online}
        activeJobs={activeJobs}
        failedJobs={failedJobs}
        fileCount={state.files?.length ?? 0}
        updateAttention={updateAttention}
        environmentAttention={environment.showBanner}
        onNavigate={navigate}
        onDoctor={() => setDoctorOpen(true)}
        onUpdate={() => setUpdateOpen(true)}
        onOpenFolder={openFolderFromUi}
      />
      <Header
        title={viewCopy[view].title}
        description={viewCopy[view].description}
        version={state.version}
        online={online}
        updateAttention={updateAttention}
        environmentAttention={environment.showBanner}
        notification={notifyMode}
        onDoctor={() => setDoctorOpen(true)}
        onUpdate={() => setUpdateOpen(true)}
        onOpenFolder={openFolderFromUi}
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

      <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6">
        {view === 'new' && (
          <div className="max-w-3xl">
            <NewDownloadPanel
              options={options}
              onOptionsChange={patchOptions}
              playwright={state.playwright}
              onToast={toast}
              onAdded={refresh}
            />
          </div>
        )}
        {view === 'queue' && (
          <QueuePanel jobs={jobs} windowMode={!!state.window} onChanged={refresh} onToast={toast} />
        )}
        {view === 'auto-download' && (
          <SubscriptionsPanel
            options={options}
            subscriptions={subscriptions}
            intervalSeconds={intervalSeconds}
            onChanged={refreshSubs}
            onToast={toast}
          />
        )}
        {view === 'library' && (
          <FileGallery
            files={state.files ?? []}
            windowMode={!!state.window}
            onRefresh={refreshFiles}
            onToast={toast}
          />
        )}
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
