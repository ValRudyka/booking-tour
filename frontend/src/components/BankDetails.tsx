import { Descriptions, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import type { BankDetails } from '../api/types'
import { formatKyivDateTime, formatMoney } from '../utils/format'

/** Bank transfer details, every value copyable (spec 05): the payment page after «Отримати
 * реквізити» and the client's order page while that transfer is still pending (spec 06). */
export function BankDetailsTable({ details }: { details: BankDetails }) {
  const { t } = useTranslation()
  const value = (field: string, shown: string, text: string = shown) => (
    <Typography.Text copyable={{ text, tooltips: [t('payment.bank.copy', { field }), t('payment.bank.copied')] }}>
      {shown}
    </Typography.Text>
  )
  return (
    <Descriptions bordered column={1} size="small" items={[
      { key: 'recipient', label: t('payment.bank.recipient'), children: value(t('payment.bank.recipient'), details.recipient) },
      { key: 'iban', label: t('payment.bank.iban'), children: value(t('payment.bank.iban'), details.iban) },
      { key: 'edrpou', label: t('payment.bank.edrpou'), children: value(t('payment.bank.edrpou'), details.edrpou) },
      { key: 'bank', label: t('payment.bank.bankName'), children: value(t('payment.bank.bankName'), details.bank_name) },
      {
        key: 'amount', label: t('payment.bank.amount'),
        // Banks expect "77500.00": the exact decimal string from the API is copied.
        children: value(t('payment.bank.amount'), t('checkout.summary.amount', { amount: formatMoney(details.amount_uah) }), details.amount_uah),
      },
      { key: 'purpose', label: t('payment.bank.purpose'), children: value(t('payment.bank.purpose'), details.purpose) },
      ...(details.pay_until ? [{
        key: 'until', label: t('payment.bank.payUntil'), children: formatKyivDateTime(details.pay_until),
      }] : []),
    ]} />
  )
}
