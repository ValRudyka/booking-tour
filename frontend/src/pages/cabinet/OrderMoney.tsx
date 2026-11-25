import { Card, Flex, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { OrderDetailWithPrice, PaymentShort } from '../../api/types'
import { StatusTag } from '../../components/StatusTag'
import { paymentMethodLabel } from '../../constants/orderLabels'
import { formatKyivDateTime, formatMoney } from '../../utils/format'

/**
 * Money of the order as the API returns it (ТЗ 4.5.6): the payment status, each payment and each
 * refund row (amount, method, status), and the ФПВ once finance has set it. Nothing is summed
 * here: amounts are decimal strings, only formatted. Failed refund rows are not shown to the
 * client: finance repeats the refund as a new row, and the client sees it as «В обробці».
 */
export function OrderMoney({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const payments = order.payments.filter((p) => p.type === 'payment' && p.status === 'succeeded')
  const refunds = order.payments.filter((p) => p.type === 'refund' && p.status !== 'failed')
  // Informational texts only (no buttons): what happens next with the money.
  const note = order.status === 'cancel_requested' && refunds.length === 0 ? t('cabinet.money.requested')
    : order.status === 'rejected' && refunds.length === 0 ? t('cabinet.money.rejectedFull') : null
  if (payments.length === 0 && refunds.length === 0 && !order.fpv_uah && !note) return null

  const amount = (value: string) => t('checkout.summary.amount', { amount: formatMoney(value) })
  const row = (p: PaymentShort, method: string) => (
    <Flex key={p.id} gap={8} wrap align="center" className="money-row">
      <Typography.Text strong>{amount(p.paid_amount ?? p.amount_uah)}</Typography.Text>
      <Typography.Text>{method}</Typography.Text>
      <StatusTag kind="transaction" status={p.status} />
      <Typography.Text type="secondary">{formatKyivDateTime(p.received_at ?? p.created_at)}</Typography.Text>
    </Flex>
  )

  return (
    <Card className="order-section" title={<h2 className="cabinet-section-title">{t('cabinet.money.title')}</h2>}>
      <dl className="order-facts">
        <dt>{t('cabinet.money.paymentStatus')}</dt>
        <dd><StatusTag kind="payment" status={order.payment_status} /></dd>
      </dl>
      {payments.length > 0 && (
        <section aria-label={t('cabinet.money.payments')}>
          <h3 className="money-subtitle">{t('cabinet.money.payments')}</h3>
          {payments.map((p) => row(p, paymentMethodLabel(t, p.method)))}
        </section>
      )}
      {refunds.length > 0 && (
        <section aria-label={t('cabinet.money.refunds')}>
          <h3 className="money-subtitle">{t('cabinet.money.refunds')}</h3>
          {refunds.map((p) => row(p, t(`cabinet.money.refundMethod.${p.method}`)))}
        </section>
      )}
      {order.fpv_uah && (
        <Typography.Paragraph className="money-fpv">{t('cabinet.money.fpv', { amount: formatMoney(order.fpv_uah) })}</Typography.Paragraph>
      )}
      {note && <Typography.Paragraph type="secondary" className="money-fpv">{note}</Typography.Paragraph>}
    </Card>
  )
}
