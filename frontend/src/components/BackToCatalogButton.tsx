import { Button } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'

export function BackToCatalogButton() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return <Button type="primary" onClick={() => navigate('/tours')}>{t('app.toCatalog')}</Button>
}
