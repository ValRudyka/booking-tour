import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Flex, Result, Skeleton, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router'
import { ApiError } from '../../api/client'
import { useOrderReview } from '../../api/cabinet'
import { useOrder } from '../../api/payments'
import type { MyReview, OrderDetailWithPrice, OrderReview } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { StarIcons } from '../../components/StarIcons'
import { StatusTag } from '../../components/StatusTag'
import { parseOrderId } from '../../features/payment/paymentPaths'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { usePrivateImage } from '../../hooks/usePrivateImage'
import { formatKyivDateTime } from '../../utils/format'
import { OrderQueryState } from '../payment/paymentShared'
import { orderPath } from './cabinetPaths'
import { ReviewForm } from './ReviewForm'
import './CabinetPages.css'

const notFound = new ApiError('not_found', 404, '')

/**
 * «Відгук про подорож» (ТЗ 4.5.7, form 4.6.1.4). What is possible comes from the API
 * (GET /orders/{id}/review): a new review when `can_write`; otherwise the review that exists,
 * with its moderation status, and one correction after a rejection (`can_resubmit`).
 */
export function ReviewPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('review.title'))
  const orderId = parseOrderId(useParams().id)
  const order = useOrder(orderId)
  const state = useOrderReview(orderId ?? 0, orderId !== null)

  if (orderId === null) return <OrderQueryState error={notFound} onRetry={() => undefined} />
  if (!order.data) return <OrderQueryState error={order.error} onRetry={() => void order.refetch()} />
  if (state.isError) {
    return <ApiErrorState error={state.error} onRetry={() => void state.refetch()} title={t('review.title')} />
  }
  if (!state.data) return <Skeleton active={false} paragraph={{ rows: 8 }} />
  return <ReviewContent order={order.data} state={state.data} />
}

function ReviewContent({ order, state }: { order: OrderDetailWithPrice; state: OrderReview }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const review = state.review
  const back = (
    <Button type="link" icon={<ArrowLeftOutlined aria-hidden />} className="order-back"
      onClick={() => navigate(orderPath(order.id))}>
      {t('review.backToOrder')}
    </Button>
  )
  const header = (
    <>
      {back}
      <h1 className="cabinet-title">{t('review.title')}</h1>
      <Typography.Paragraph>
        <Typography.Text strong>{order.tour_title_uk}</Typography.Text>
        {' · '}{t('review.order', { number: order.number })}
      </Typography.Paragraph>
    </>
  )

  if (!review && !state.can_write) {
    return (
      <>
        {back}
        <Result status="info" title={<h1 className="result-title">{t('review.notAllowedTitle')}</h1>}
          subTitle={t('review.notAllowedText')} />
      </>
    )
  }
  if (!review || (editing && review.can_resubmit)) {
    return (
      <>
        {header}
        <ReviewForm orderId={order.id} state={state} existing={editing ? review : null}
          onCancel={editing ? () => setEditing(false) : undefined}
          onDone={() => setEditing(false)} />
      </>
    )
  }
  return (
    <>
      {header}
      <ReviewView review={review} onEdit={() => setEditing(true)} />
    </>
  )
}

/** The review as written, with its moderation status (no editing by anyone but its author, once). */
function ReviewView({ review, onEdit }: { review: MyReview; onEdit: () => void }) {
  const { t } = useTranslation()
  const statusText = review.status === 'pending' ? t('review.pendingText')
    : review.status === 'published' ? t('review.publishedText') : null
  return (
    <Card>
      <Flex gap={8} wrap align="center" className="review-status">
        <Typography.Text strong>{t('review.status')}:</Typography.Text>
        <StatusTag kind="review" status={review.status} />
        <Typography.Text type="secondary">
          {t('review.submittedAt', { date: formatKyivDateTime(review.submitted_at) })}
        </Typography.Text>
      </Flex>
      {statusText && <Typography.Paragraph>{statusText}</Typography.Paragraph>}
      {review.status === 'rejected' && (
        <Alert type={review.can_resubmit ? 'warning' : 'error'} showIcon className="review-reject"
          title={review.reject_reason ? t('review.rejectReason', { reason: review.reject_reason }) : t('reviewStatus.rejected')}
          description={review.can_resubmit ? t('review.canResubmit') : t('review.noResubmit')}
          action={review.can_resubmit ? <Button onClick={onEdit}>{t('review.edit')}</Button> : undefined} />
      )}
      <dl className="order-facts">
        <dt>{t('review.hotelRating')}</dt>
        <dd><StarIcons value={review.hotel_rating} outOf={5} label={t('review.ratingValue', { value: review.hotel_rating })} /></dd>
        <dt>{t('review.serviceRating')}</dt>
        <dd><StarIcons value={review.service_rating} outOf={5} label={t('review.ratingValue', { value: review.service_rating })} /></dd>
        <dt>{t('review.nameDisplay')}</dt>
        <dd>{review.author}</dd>
      </dl>
      {review.positive && (
        <><h2 className="money-subtitle">{t('review.positiveTitle')}</h2><Typography.Paragraph>{review.positive}</Typography.Paragraph></>
      )}
      {review.negative && (
        <><h2 className="money-subtitle">{t('review.negativeTitle')}</h2><Typography.Paragraph>{review.negative}</Typography.Paragraph></>
      )}
      {!review.positive && !review.negative && <Typography.Paragraph type="secondary">{t('review.noText')}</Typography.Paragraph>}
      {review.photos.length > 0 && (
        <div className="review-photos">
          {review.photos.map((photo, n) => <PrivatePhoto key={photo.id} path={photo.url} alt={t('review.photoAlt', { n: n + 1 })} />)}
        </div>
      )}
    </Card>
  )
}

function PrivatePhoto({ path, alt }: { path: string; alt: string }) {
  const url = usePrivateImage(path)
  return url ? <img src={url} alt={alt} className="review-photo" /> : <span className="review-photo" role="img" aria-label={alt} />
}
