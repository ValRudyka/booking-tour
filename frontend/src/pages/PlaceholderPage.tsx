import { Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { BackToCatalogButton } from '../components/BackToCatalogButton'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

export type PlaceholderKey = 'about' | 'terms' | 'privacy' | 'profile' | 'office'

/** Stub for pages that come in later steps (static pages, personal account, back office). */
export function PlaceholderPage({ page }: { page: PlaceholderKey }) {
  const { t } = useTranslation()
  const title = t(`pages.${page}`)
  useDocumentTitle(title)
  return (
    <Result status="info" title={<h1 className="result-title">{title}</h1>}
      subTitle={t('pages.placeholderText')} extra={<BackToCatalogButton />} />
  )
}
