import React from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App'
import { I18nProvider } from './i18n'
import { applyTheme, readTheme } from './hooks/useTheme'
import { QuickDownloadApp } from './components/download/QuickDownload'

applyTheme(readTheme())

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>{window.location.hash === '#/quick' ? <QuickDownloadApp /> : <App />}</I18nProvider>
  </React.StrictMode>,
)
