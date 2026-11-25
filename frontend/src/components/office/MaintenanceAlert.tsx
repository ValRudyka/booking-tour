import { Alert } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { useAdminSettings } from '../../api/admin'

/**
 * Above every back-office page while maintenance mode is on (spec 13 §3). Only admins can work
 * then (backend services/maintenance.py: managers and finance get 503 like clients), so only the
 * admin's layout renders it; it reads GET /admin/settings, which saving the setting refreshes.
 */
export function MaintenanceAlert() {
  const { t } = useTranslation()
  const settings = useAdminSettings()
  if (!settings.data?.maintenance_mode) return null
  return (
    <Alert type="warning" showIcon role="status" className="office-maintenance-alert"
      title={t('admin.maintenance.alertTitle')}
      description={<>{t('admin.maintenance.alertText')} <Link to="/office/settings#maintenance">{t('admin.maintenance.alertLink')}</Link></>} />
  )
}
