import { Button, Result } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { formatDate } from '../utils/format'

/** /booking/:tourId?date=YYYY-MM-DD — stand-in until the checkout page (feature/frontend-public). */
export function BookingPlaceholder() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { tourId = '' } = useParams()
  const [params] = useSearchParams()
  const date = params.get('date') ?? ''
  const title = t('booking.placeholderTitle', { id: tourId })
  useDocumentTitle(title)
  return (
    <Result status="info" title={<h1 className="result-title">{title}</h1>}
      subTitle={t('booking.placeholderText', { date: /^\d{4}-\d{2}-\d{2}$/.test(date) ? formatDate(date) : '—' })}
      extra={<Button type="primary" onClick={() => navigate(`/tours/${tourId}`)}>{t('booking.backToTour')}</Button>} />
  )
}
