import { Loader2 } from 'lucide-react'

export function RestartOverlay({ windowMode }: { windowMode: boolean }) {
  return (
    <div
      role="alert"
      className="fixed inset-0 z-[70] grid place-items-center bg-black/80 p-6 text-center backdrop-blur"
    >
      <div>
        <Loader2 className="mx-auto mb-4 animate-spin" size={30} />
        <p className="font-medium">Restarting the service…</p>
        <p className="mt-1 text-sm text-zinc-400">
          {windowMode
            ? 'This window will close and a new one will open.'
            : 'This page reloads automatically when it is back.'}
        </p>
      </div>
    </div>
  )
}
