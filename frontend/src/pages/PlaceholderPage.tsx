import { Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { BackToCatalogButton } from '../components/BackToCatalogButton'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

export type PlaceholderKey = 'about' | 'login' | 'register' | 'terms' | 'privacy' | 'cabinet' | 'cabinetOrders' | 'office'

/** Stub for pages that come in later steps (auth, static pages). */
export function PlaceholderPage({ page }: { page: PlaceholderKey }) {
  const { t } = useTranslation()
  const title = t(`pages.${page}`)
  useDocumentTitle(title)
  return (
    <Result status="info" title={<h1 className="result-title">{title}</h1>}
      subTitle={t('pages.placeholderText')} extra={<BackToCatalogButton />} />
  )
}
