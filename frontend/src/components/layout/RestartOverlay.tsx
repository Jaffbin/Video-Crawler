import { Loader2 } from 'lucide-react'
import { useI18n } from '../../i18n'

export function RestartOverlay({ windowMode }: { windowMode: boolean }) {
  const { t } = useI18n()
  return (
    <div
      role="alert"
      className="fixed inset-0 z-[70] grid place-items-center bg-black/80 p-6 text-center backdrop-blur"
    >
      <div>
        <Loader2 className="mx-auto mb-4 animate-spin" size={30} />
        <p className="font-medium">{t('Restarting the service…')}</p>
        <p className="mt-1 text-sm text-zinc-400">
          {windowMode
            ? t('This window will close and a new one will open.')
            : t('This page reloads automatically when it is back.')}
        </p>
      </div>
    </div>
  )
}
