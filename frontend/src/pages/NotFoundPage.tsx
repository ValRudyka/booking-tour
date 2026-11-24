import { Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { BackToCatalogButton } from '../components/BackToCatalogButton'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

export function NotFoundPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('pages.notFoundTitle'))
  return (
    <Result status="404" title={<h1 className="result-title">{t('pages.notFoundTitle')}</h1>}
      subTitle={t('pages.notFoundText')} extra={<BackToCatalogButton />} />
  )
}
