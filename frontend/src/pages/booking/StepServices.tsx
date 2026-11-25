import { Alert, Button, Flex, Form, Input, Radio, Skeleton, Space } from 'antd'
import { useTranslation } from 'react-i18next'
import type { Price, ServiceOption } from '../../api/types'
import { MAX_WISHES } from '../../features/booking/bookingRules'
import { formatMoney } from '../../utils/format'

interface Props {
  insurance: ServiceOption[] | undefined
  transfer: ServiceOption[] | undefined
  price: Price | null
  /** The code the order has now (null = none). */
  appliedPromo: string | null
  promoError: string | null
  busy: boolean
  onInsurance: (id: number) => void
  onTransfer: (id: number) => void
  onApplyPromo: () => void
  onRemovePromo: () => void
}

/** Step 3 (form 4.6.1.2, fields 4–7): insurance, transfer, wishes and the promo code. Every choice
 * is saved on the order at once and the summary shows the server's new price. */
export function StepServices({
  insurance, transfer, price, appliedPromo, promoError, busy, onInsurance, onTransfer, onApplyPromo, onRemovePromo,
}: Props) {
  const { t } = useTranslation()
  return (
    <>
      <Form.Item name="insurance_type_id" label={t('checkout.services.insurance')}>
        {insurance ? (
          <Radio.Group disabled={busy} onChange={(e) => onInsurance(e.target.value as number)}>
            <Flex vertical gap={8}>
              {insurance.map((option) => (
                <Radio key={option.id} value={option.id}>
                  {t('checkout.services.insuranceOption', { name: option.name_uk, price: formatMoney(option.price_uah) })}
                </Radio>
              ))}
            </Flex>
          </Radio.Group>
        ) : <Skeleton active={false} paragraph={{ rows: 2 }} title={false} />}
      </Form.Item>
      <Form.Item name="transfer_type_id" label={t('checkout.services.transfer')}>
        {transfer ? (
          <Radio.Group disabled={busy} onChange={(e) => onTransfer(e.target.value as number)}>
            <Flex vertical gap={8}>
              {transfer.map((option) => (
                <Radio key={option.id} value={option.id}>
                  {t('checkout.services.transferOption', { name: option.name_uk, price: formatMoney(option.price_uah) })}
                </Radio>
              ))}
            </Flex>
          </Radio.Group>
        ) : <Skeleton active={false} paragraph={{ rows: 2 }} title={false} />}
      </Form.Item>

      {appliedPromo ? (
        <Alert type="success" showIcon className="booking-block"
          title={t('checkout.services.promoApplied', {
            code: appliedPromo, amount: formatMoney(price?.discount_uah ?? '0.00'),
          })}
          action={<Button size="small" disabled={busy} onClick={onRemovePromo}>{t('checkout.services.promoRemove')}</Button>} />
      ) : (
        <Form.Item label={t('checkout.services.promo')} htmlFor="booking-promo"
          validateStatus={promoError ? 'error' : undefined} help={promoError ?? undefined}>
          <Space.Compact style={{ width: '100%', maxWidth: 360 }}>
            <Form.Item name="promo" noStyle>
              <Input id="booking-promo" autoComplete="off" maxLength={20}
                aria-invalid={promoError ? true : undefined} onPressEnter={(e) => { e.preventDefault(); onApplyPromo() }} />
            </Form.Item>
            <Button onClick={onApplyPromo} loading={busy}>{t('checkout.services.promoApply')}</Button>
          </Space.Compact>
        </Form.Item>
      )}

      <Form.Item name="wishes" label={t('checkout.services.wishes')}
        rules={[{ max: MAX_WISHES, message: t('checkout.rules.wishes') }]}>
        <Input.TextArea rows={3} maxLength={MAX_WISHES} showCount placeholder={t('checkout.services.wishesPlaceholder')} />
      </Form.Item>
    </>
  )
}
