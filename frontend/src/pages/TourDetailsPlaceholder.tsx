import { Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { BackToCatalogButton } from '../components/BackToCatalogButton'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** /tours/:id — the tour page itself is the next frontend task. */
export function TourDetailsPlaceholder() {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const title = t('pages.tourTitle', { id })
  useDocumentTitle(title)
  return (
    <Result status="info" title={<h1 className="result-title">{title}</h1>}
      subTitle={t('pages.tourText')} extra={<BackToCatalogButton />} />
  )
}
