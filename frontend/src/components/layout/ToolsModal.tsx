import { FolderOpen, RefreshCw, Stethoscope } from 'lucide-react'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { ExtensionAccess } from './ExtensionAccess'

interface Props {
  open: boolean
  onClose: () => void
  onDoctor: () => void
  onUpdate: () => void
  onOpenFolder: () => void
  onBackup?: () => void
  updateAttention: boolean
  environmentAttention: boolean
}

export function ToolsModal(p: Props) {
  const { t } = useI18n()
  return (
    <Modal open={p.open} onClose={p.onClose} title={t('Settings and help')}>
      <div className="grid gap-4">
        {p.onBackup && <Button onClick={p.onBackup}>{t('Backup and restore')}</Button>}
        <Button onClick={p.onOpenFolder}>
          <FolderOpen aria-hidden size={18} />
          {t('Open folder')}
        </Button>
        <Button onClick={p.onUpdate}>
          <RefreshCw aria-hidden size={18} />
          {t('Updates')}
          {p.updateAttention && (
            <>
              {' '}
              <span className="text-amber-300">{t('Needs attention')}</span>
            </>
          )}
        </Button>
        <Button onClick={p.onDoctor}>
          <Stethoscope aria-hidden size={18} />
          {t('Diagnostics')}
          {p.environmentAttention && (
            <>
              {' '}
              <span className="text-amber-300">{t('Needs attention')}</span>
            </>
          )}
        </Button>
        <ExtensionAccess />
      </div>
    </Modal>
  )
}
