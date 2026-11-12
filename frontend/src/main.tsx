import React from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App'
import { I18nProvider } from './i18n'
import { applyTheme, readTheme } from './hooks/useTheme'
import { QuickDownloadApp } from './components/download/QuickDownload'

applyTheme(readTheme())

// The launch link (?n=...) only needs to work once: the session cookie keeps reloads working, so keep it
// out of the address bar and history.
if (new URLSearchParams(window.location.search).has('n')) {
  const url = new URL(window.location.href)
  url.searchParams.delete('n')
  window.history.replaceState(null, '', url.pathname + url.search + url.hash)
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>{window.location.hash === '#/quick' ? <QuickDownloadApp /> : <App />}</I18nProvider>
  </React.StrictMode>,
)
