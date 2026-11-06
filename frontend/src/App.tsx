import { useCallback, useEffect, useMemo, useRef, useState, lazy, Suspense } from 'react'
import { loadOptions, saveOptions } from './lib/options'
import {
  getSetupStatus,
  getUpdateStatus,
  openFolder,
  prepareSetup,
  selectDownloadFolder,
  startYtdlpUpdate,
} from './api/client'
import { Banners } from './components/layout/Banners'
import { Header, type NotificationMode } from './components/layout/Header'
import { Sidebar } from './components/layout/Sidebar'
import { SetupGuide } from './components/layout/SetupGuide'
import { RestartOverlay } from './components/layout/RestartOverlay'
import { NewDownloadPanel } from './components/download/NewDownloadPanel'
import { QueuePanel } from './components/queue/QueuePanel'
import { Toasts } from './components/ui/Toast'
import { LanguageMenu } from './components/layout/LanguageMenu'
import { MoreToolsMenu } from './components/layout/MoreToolsMenu'

const SubscriptionsPanel = lazy(() =>
  import('./components/subscriptions/SubscriptionsPanel').then((m) => ({ default: m.SubscriptionsPanel })),
)
const FileGallery = lazy(() =>
  import('./components/files/FileGallery').then((m) => ({ default: m.FileGallery })),
)
const DiagnosticsModal = lazy(() =>
  import('./components/diagnostics/DiagnosticsModal').then((m) => ({ default: m.DiagnosticsModal })),
)
const UpdateModal = lazy(() =>
  import('./components/diagnostics/UpdateModal').then((m) => ({ default: m.UpdateModal })),
)
const ToolsModal = lazy(() =>
  import('./components/layout/ToolsModal').then((m) => ({ default: m.ToolsModal })),
)
const BackupModal = lazy(() =>
  import('./components/layout/BackupModal').then((m) => ({ default: m.BackupModal })),
)
import { useStatePolling } from './hooks/useStatePolling'
import { useCompletionNotifier } from './hooks/useCompletionNotifier'
import { useEnvironment } from './hooks/useEnvironment'
import { useRestart } from './hooks/useRestart'
import { useSubscriptions } from './hooks/useSubscriptions'
import { useToasts } from './hooks/useToasts'
import { useNavigation, type AppView } from './hooks/useNavigation'
import type { ComponentExtras, DownloadOptions, YtdlpCheck } from './types/api'
import { useI18n } from './i18n'
import { useTheme } from './hooks/useTheme'
import { useDesktopLocale } from './lib/desktop'
import { CloseBehavior } from './components/layout/CloseBehavior'
import { setNativeNotifications } from './api/client'
import { browserPreferences } from './lib/backup'
import { AudioPlayerBar, AudioPlayerProvider, useAudioLibrary } from './components/audio/AudioPlayer'

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

function AppContent() {
  useDesktopLocale()
  const { t, setLocale } = useI18n()
  const { theme, toggleTheme, restoreTheme } = useTheme()
  const { state, online, refresh, refreshFiles } = useStatePolling()
  const audio = useAudioLibrary(state.root, state.files ?? [])
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
  const notificationBusy = useRef(false)
  async function changeNotifications() {
    if (!state.native_notifications) return requestNotify()
    if (notificationBusy.current) return
    notificationBusy.current = true
    try {
      await setNativeNotifications(!state.native_notifications.enabled)
      await refresh()
    } catch (error) {
      toast(t(error instanceof Error ? error.message : 'Could not save notification preferences.'), true)
    } finally {
      notificationBusy.current = false
    }
  }
  const [doctorOpen, setDoctorOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [backupOpen, setBackupOpen] = useState(false)
  const [closeSettingsOpen, setCloseSettingsOpen] = useState(false)
  const [languageAnchor, setLanguageAnchor] = useState<HTMLElement | null>(null)
  const [moreToolsAnchor, setMoreToolsAnchor] = useState<HTMLElement | null>(null)
  const [setupOpen, setSetupOpen] = useState(false)
  const setupConsidered = useRef(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [installBusy, setInstallBusy] = useState(false)
  const [setupStage, setSetupStage] = useState('checking')
  const [downloadFocus, setDownloadFocus] = useState(0)
  const [changingFolder, setChangingFolder] = useState(false)
  const [ytdlpCheck, setYtdlpCheck] = useState<YtdlpCheck | null>(null)
  const { view, navigate } = useNavigation()

  useEffect(() => {
    if (setupConsidered.current || !environment.doctor || !state.root || !online) return
    setupConsidered.current = true
    try {
      if (localStorage.getItem('grab-setup-seen') && !localStorage.getItem('grab-setup-pending')) return
    } catch {
      // Show the guide once per session when storage is unavailable.
    }
    const hasSubscriptions = environment.doctor.checks?.some((check) => check.id === 'subscriptions')
    let resume = false
    try {
      resume = localStorage.getItem('grab-setup-pending') === '1'
    } catch {
      /* session-only guide */
    }
    if (resume || (!state.jobs.length && !state.files?.length && !hasSubscriptions)) setSetupOpen(true)
  }, [environment.doctor, state.root, state.jobs, state.files, online])

  function closeSetup() {
    try {
      localStorage.setItem('grab-setup-seen', '1')
      localStorage.removeItem('grab-setup-pending')
    } catch {
      /* storage may be disabled */
    }
    setSetupOpen(false)
  }

  useCompletionNotifier(state.jobs, {
    serverNotifies: !!state.desktop_notifications,
    nativeManaged: !!state.native_notifications,
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
        if (s.status === 'error') throw new Error(s.error || 'Install failed')
        if (s.status !== 'running') break
        await new Promise((r) => setTimeout(r, 900))
      }
      await environment.refresh()
      toast(t('Components installed. Open Update to restart the service.'))
    } catch (e) {
      toast(e instanceof Error ? e.message : t('Install failed'), true)
    } finally {
      setInstallBusy(false)
    }
  }

  async function prepare() {
    setInstallBusy(true)
    setSetupStage('checking')
    try {
      try {
        localStorage.setItem('grab-setup-pending', '1')
      } catch {
        /* Preparation works without storage. */
      }
      await prepareSetup()
      for (;;) {
        const status = await getUpdateStatus()
        setSetupStage(status.setup_stage || 'checking')
        if (status.status === 'error')
          throw new Error('Preparation failed. Check your connection or open technical details.')
        if (status.status !== 'running') break
        await new Promise((resolve) => setTimeout(resolve, 900))
      }
      const status = await getSetupStatus()
      await environment.refresh()
      await refresh()
      if (status.restart_required) await restartService()
      else if (!status.ready)
        throw new Error('Some download features still need attention. Open technical details for help.')
    } finally {
      setInstallBusy(false)
    }
  }

  async function changeFolder() {
    setChangingFolder(true)
    try {
      const result = await selectDownloadFolder()
      if (!result.canceled && result.restart_required) await restartService()
    } catch (e) {
      toast(t(e instanceof Error ? e.message : 'Could not change the save folder. Please try again.'), true)
    } finally {
      setChangingFolder(false)
    }
  }

  const jobs = useMemo(() => state.jobs, [state.jobs])
  const activeJobs = jobs.filter((job) => job.status === 'queued' || job.status === 'running').length
  const failedJobs = jobs.filter((job) => job.status === 'error' || job.status === 'canceled').length
  const viewCopy: Record<AppView, { title: string; description: string }> = {
    new: { title: t('New download'), description: t('Add one or more video, playlist, MP4 or M3U8 links.') },
    queue: {
      title: t('Queue'),
      description: t('Track active jobs and review completed or failed downloads.'),
    },
    'auto-download': {
      title: t('Auto-download'),
      description: t('Watch channels and playlists for newly published videos.'),
    },
    library: { title: t('Library'), description: t('Browse files saved in your download folder.') },
  }

  const openFolderFromUi = () =>
    openFolder().catch((e) => toast(e instanceof Error ? e.message : t('Could not open the folder'), true))

  return (
    <div className="app-shell flex h-dvh min-h-0 flex-col overflow-hidden pb-20 lg:pb-0 lg:pl-60">
      <Sidebar
        onSetup={() => setSetupOpen(true)}
        onCloseBehavior={state.window ? () => setCloseSettingsOpen(true) : undefined}
        onLanguage={setLanguageAnchor}
        view={view}
        version={state.version}
        online={online}
        activeJobs={activeJobs}
        failedJobs={failedJobs}
        fileCount={state.files?.length ?? 0}
        updateAttention={updateAttention}
        environmentAttention={environment.showBanner}
        onNavigate={navigate}
        onTools={() => setToolsOpen(true)}
        onOpenFolder={openFolderFromUi}
      />
      <Header
        onLanguage={(button) => {
          setMoreToolsAnchor(null)
          setLanguageAnchor(button)
        }}
        onMoreTools={(button) => {
          setLanguageAnchor(null)
          setMoreToolsAnchor((current) => (current ? null : button))
        }}
        moreToolsOpen={!!moreToolsAnchor}
        theme={theme}
        onToggleTheme={toggleTheme}
        title={viewCopy[view].title}
        description={viewCopy[view].description}
        version={state.version}
        online={online}
        updateAttention={updateAttention}
        environmentAttention={environment.showBanner}
        notification={
          state.native_notifications
            ? state.native_notifications.enabled
              ? 'native-on'
              : 'native-off'
            : notifyMode
        }
        onTools={() => setToolsOpen(true)}
        onNotify={() => void changeNotifications()}
      />
      <div className="max-h-[30dvh] shrink-0 overflow-y-auto">
        <Banners
          onOpenSetup={() => setSetupOpen(true)}
          online={online}
          ffmpeg={state.ffmpeg}
          showYoutubeIssues={environment.showBanner}
          onOpenDiagnostics={() => setDoctorOpen(true)}
          onDismissYoutubeIssues={environment.dismiss}
        />
      </div>

      <main
        className={`app-content mx-auto min-h-0 w-full max-w-[1500px] flex-1 px-4 py-4 sm:px-6 ${view === 'new' ? 'download-view' : 'overflow-y-auto'}`}
      >
        {view === 'new' && (
          <NewDownloadPanel
            focusLinks={downloadFocus}
            root={state.root}
            onChooseFolder={changeFolder}
            changingFolder={changingFolder}
            folderChangeBlocked={activeJobs > 0 || installBusy}
            options={options}
            onOptionsChange={patchOptions}
            playwright={state.playwright}
            onToast={toast}
            onAdded={() => {
              void refresh()
              navigate('queue')
            }}
          />
        )}
        {view === 'queue' && (
          <QueuePanel
            jobs={jobs}
            queuePaused={state.queue_paused}
            queueOrder={state.queue_order}
            onNewDownload={() => navigate('new')}
            windowMode={!!state.window}
            onChanged={refresh}
            onToast={toast}
            onHelp={() => setSetupOpen(true)}
          />
        )}
        {view === 'auto-download' && (
          <Suspense fallback={<p role="status">{t('Connecting…')}</p>}>
            <SubscriptionsPanel
              options={options}
              subscriptions={subscriptions}
              intervalSeconds={intervalSeconds}
              onChanged={refreshSubs}
              onToast={toast}
            />
          </Suspense>
        )}
        {view === 'library' && !state.root && <p role="status">{t('Connecting…')}</p>}
        {view === 'library' && !!state.root && (
          <Suspense fallback={<p role="status">{t('Connecting…')}</p>}>
            <FileGallery
              audioPlayer={audio}
              key={state.root}
              root={state.root}
              files={state.files ?? []}
              scan={state.library_scan}
              collections={state.collections ?? []}
              smartCollections={state.smart_collections ?? []}
              onNewDownload={() => navigate('new')}
              editingBlocked={jobs.some((job) => job.status === 'running')}
              windowMode={!!state.window}
              onRefresh={refreshFiles}
              onToast={toast}
            />
          </Suspense>
        )}
      </main>

      <AudioPlayerBar windowMode={!!state.window} />

      {languageAnchor && <LanguageMenu anchor={languageAnchor} onClose={() => setLanguageAnchor(null)} />}
      {moreToolsAnchor && (
        <MoreToolsMenu
          anchor={moreToolsAnchor}
          onClose={() => setMoreToolsAnchor(null)}
          onSetup={() => setSetupOpen(true)}
          onCloseBehavior={state.window ? () => setCloseSettingsOpen(true) : undefined}
        />
      )}
      {toolsOpen && (
        <Suspense fallback={null}>
          <ToolsModal
            open={toolsOpen}
            onClose={() => setToolsOpen(false)}
            updateAttention={updateAttention}
            environmentAttention={environment.showBanner}
            onDoctor={() => {
              setToolsOpen(false)
              setDoctorOpen(true)
            }}
            onUpdate={() => {
              setToolsOpen(false)
              setUpdateOpen(true)
            }}
            onOpenFolder={openFolderFromUi}
            onBackup={() => {
              setToolsOpen(false)
              setBackupOpen(true)
            }}
          />
        </Suspense>
      )}
      {backupOpen && (
        <Suspense fallback={null}>
          <BackupModal
            open={backupOpen}
            onClose={() => setBackupOpen(false)}
            onRestored={() => {
              setOptions(loadOptions())
              const restored = browserPreferences()
              if (restored.locale) setLocale(restored.locale)
              restoreTheme()
              void refreshFiles()
            }}
          />
        </Suspense>
      )}

      {doctorOpen && (
        <Suspense fallback={null}>
          <DiagnosticsModal
            open={doctorOpen}
            onClose={() => setDoctorOpen(false)}
            doctor={environment.doctor}
            onRefresh={environment.refresh}
            onInstall={install}
            installBusy={installBusy}
            onToast={toast}
          />
        </Suspense>
      )}
      <SetupGuide
        open={setupOpen}
        doctor={environment.doctor}
        onClose={closeSetup}
        onDiagnostics={() => {
          closeSetup()
          setDoctorOpen(true)
        }}
        preparing={installBusy}
        preparationStage={setupStage}
        onLibrary={() => {
          closeSetup()
          navigate('library')
        }}
        onPrepare={prepare}
        onStart={(imagesOnly) => {
          if (imagesOnly) patchOptions({ mode: 'image' })
          closeSetup()
          navigate('new')
          setDownloadFocus((key) => key + 1)
        }}
      />
      {updateOpen && (
        <Suspense fallback={null}>
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
        </Suspense>
      )}

      <CloseBehavior
        pendingDownloads={activeJobs}
        settingsOpen={closeSettingsOpen}
        onCloseSettings={() => setCloseSettingsOpen(false)}
      />
      {restarting && <RestartOverlay windowMode={!!state.window} />}
      <Toasts items={toasts} onRemove={remove} />
    </div>
  )
}

export default function App() {
  return (
    <AudioPlayerProvider>
      <AppContent />
    </AudioPlayerProvider>
  )
}
