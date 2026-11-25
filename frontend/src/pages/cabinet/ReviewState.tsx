import { Button, Flex } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import type { OrderSummary } from '../../api/types'
import { StatusTag } from '../../components/StatusTag'
import { has, reviewPath } from './cabinetPaths'

/**
 * The review of a past trip in the order list («Історія подорожей», spec 08 §4). Everything comes
 * from the API: `review` in client_actions (a review can be written), else `review_status` and
 * `review_can_resubmit` (backend services/reviews.py can_resubmit). Nothing for other orders.
 */
export function ReviewState({ order }: { order: OrderSummary }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = () => navigate(reviewPath(order.id))

  if (has(order, 'review')) {
    return (
      <Button type="primary" size="small" onClick={open}
        aria-label={t('cabinet.history.writeOf', { number: order.number })}>
        {t('cabinet.order.review')}
      </Button>
    )
  }
  if (!order.review_status) return null
  if (order.review_status === 'rejected' && order.review_can_resubmit) {
    return (
      <Button size="small" danger onClick={open} aria-label={t('cabinet.history.fixOf', { number: order.number })}>
        {t('cabinet.history.fix')}
      </Button>
    )
  }
  return (
    <Flex gap={8} align="center" wrap>
      <span className="visually-hidden">{t('cabinet.history.reviewLabel')}</span>
      <StatusTag kind="review" status={order.review_status} />
    </Flex>
  )
}
