import { Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { BackToCatalogButton } from '../components/BackToCatalogButton'

/** Shown by the router when a page crashes while rendering. */
export function RouteErrorPage() {
  const { t } = useTranslation()
  return (
    <Result status="error" title={<h1 className="result-title">{t('errors.unexpected')}</h1>}
      subTitle={t('errors.unexpectedHint')} extra={<BackToCatalogButton />} />
  )
}
