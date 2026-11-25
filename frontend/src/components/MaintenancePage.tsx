import { ReloadOutlined, ToolOutlined } from '@ant-design/icons'
import { Button, Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../features/auth/useAuth'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import './MaintenancePage.css'

/**
 * A protected page while maintenance mode is on (form 4.6.4.1, field 7): GET /auth/me answered
 * 503 for this user (everyone but an admin). Shown by RequireAuth in place of the page, never a
 * redirect to /login. The text is the API's own 503 message. The page comes back by itself: the
 * button, window focus and a check every minute ask /auth/me again (AuthProvider).
 */
export function MaintenancePage() {
  const { t } = useTranslation()
  const { maintenanceMessage, recheck, rechecking } = useAuth()
  useDocumentTitle(t('errors.maintenanceTitle'))
  return (
    <Result className="maintenance-page" icon={<ToolOutlined aria-hidden />}
      title={<h1 className="result-title">{t('errors.maintenanceTitle')}</h1>}
      subTitle={maintenanceMessage ?? t('errors.maintenance')}
      extra={(
        <Button icon={<ReloadOutlined aria-hidden />} loading={rechecking} onClick={() => void recheck()}>
          {t('errors.retry')}
        </Button>
      )} />
  )
}
