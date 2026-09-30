import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { CheckStatus, DoctorCheck } from '../../types/api'
import { useI18n } from '../../i18n'

const ICON: Record<CheckStatus, React.ReactNode> = {
  ok: <CheckCircle2 aria-hidden size={16} className="text-emerald-400" />,
  info: <Info aria-hidden size={16} className="text-zinc-400" />,
  warn: <AlertTriangle aria-hidden size={16} className="text-amber-400" />,
  error: <XCircle aria-hidden size={16} className="text-red-400" />,
}

interface Props {
  checks: DoctorCheck[]
  onCopy: (text: string) => void
  onFix: (check: DoctorCheck) => void
  busyAction: string | null
}

export function DoctorList({ checks, onCopy, onFix, busyAction }: Props) {
  const { t } = useI18n()
  return (
    <ul className="grid gap-2">
      {checks.map((c) => (
        <li key={c.id} className="grid grid-cols-[20px_1fr] gap-3 rounded-xl bg-white/[.02] p-3">
          <div className="pt-0.5">{ICON[c.status]}</div>
          <div className="min-w-0">
            <div className="text-sm font-medium">
              {t(`check.${c.id}`) === `check.${c.id}` ? c.label : t(`check.${c.id}`)}
            </div>
            <p className="mt-0.5 text-xs leading-5 text-zinc-400">
              {t(
                c.status === 'ok'
                  ? 'Ready'
                  : c.status === 'info'
                    ? 'Optional or informational'
                    : 'Needs attention',
              )}
            </p>
            <details className="mt-1 text-xs text-zinc-500">
              <summary className="cursor-pointer">{t('Technical details')}</summary>
              <p className="mt-1 break-all">{c.detail}</p>
            </details>
            {c.fix && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <code className="overflow-auto whitespace-nowrap rounded-lg bg-black/40 px-2 py-1 text-xs">
                  {c.fix}
                </code>
                <button type="button" className="action-btn" onClick={() => onCopy(c.fix!)}>
                  {t('Copy')}
                </button>
                {c.action && (
                  <button
                    type="button"
                    className="rounded-lg bg-white px-2.5 py-1 text-xs font-medium text-black hover:bg-zinc-200 disabled:opacity-50"
                    disabled={busyAction !== null}
                    onClick={() => onFix(c)}
                  >
                    {busyAction === 'installing' ? t('Installing…') : t('Install now')}
                  </button>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
