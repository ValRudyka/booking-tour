import { Col, DatePicker, Form, Input, Row } from 'antd'
import type { Rule } from 'antd/es/form'
import type { NamePath } from 'antd/es/form/interface'
import dayjs from 'dayjs'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cleanPassportNumber, isLatinPassportName, isPassportNumber } from './bookingRules'

export type PassportField = 'last_name_lat' | 'first_name_lat' | 'birth_date' | 'passport_number' | 'expiry'

const DATE_FORMAT = 'DD.MM.YYYY'
const ISO = 'YYYY-MM-DD'

interface Props {
  /** Where each field lives in the form: the booking step keeps a list of tourists
   * ([index, 'passport_expiry']), a saved tourist a flat form ('expiry_date'). */
  name: (field: PassportField) => NamePath
  /** Rules on top of "required" (the booking step checks the age on the start date). */
  birthRules?: Rule[]
  /** Days after this ISO date cannot be picked as a birth date. */
  birthMax: string
  /** Rules on top of "required" (6 months after the return at checkout, after today when saved). */
  expiryRules?: Rule[]
  expiryExtra?: ReactNode
  /** Extra fields after the passport fields (a saved tourist's issuing authority). */
  children?: ReactNode
}

/**
 * The tourist's passport fields (form 4.6.1.2, fields 3.2–3.6 / form 4.6.1.1, fields 8.1–8.5),
 * shared by the booking step and «Збережені туристи», so both check the same way as backend
 * services/passports.py (bookingRules.ts, texts in checkout.rules).
 */
export function PassportFields({ name, birthRules = [], birthMax, expiryRules = [], expiryExtra, children }: Props) {
  const { t } = useTranslation()
  const required = { required: true, message: t('checkout.rules.required') }
  const latin = {
    validator: (_: unknown, value?: string) => (!value || isLatinPassportName(value) ? Promise.resolve()
      : Promise.reject(new Error(t('checkout.rules.latin')))),
  }
  return (
    <Row gutter={16}>
      <Col xs={24} md={12}>
        <Form.Item name={name('last_name_lat')} label={t('checkout.tourists.lastName')}
          extra={t('checkout.tourists.nameHint')} rules={[required, latin]}>
          <Input autoComplete="family-name" maxLength={100} />
        </Form.Item>
      </Col>
      <Col xs={24} md={12}>
        <Form.Item name={name('first_name_lat')} label={t('checkout.tourists.firstName')} rules={[required, latin]}>
          <Input autoComplete="given-name" maxLength={100} />
        </Form.Item>
      </Col>
      <Col xs={24} md={12}>
        <Form.Item name={name('birth_date')} label={t('checkout.tourists.birthDate')} rules={[required, ...birthRules]}>
          <DatePicker format={DATE_FORMAT} style={{ width: '100%' }}
            disabledDate={(day) => day.isAfter(dayjs(birthMax, ISO), 'day')} />
        </Form.Item>
      </Col>
      <Col xs={24} md={12}>
        <Form.Item name={name('passport_number')} label={t('checkout.tourists.passportNumber')}
          normalize={(value?: string) => (value ? cleanPassportNumber(value) : value)}
          rules={[required, {
            validator: (_, value?: string) => (!value || isPassportNumber(value) ? Promise.resolve()
              : Promise.reject(new Error(t('checkout.rules.passportNumber')))),
          }]}>
          <Input autoComplete="off" maxLength={20} />
        </Form.Item>
      </Col>
      <Col xs={24} md={12}>
        <Form.Item name={name('expiry')} label={t('checkout.tourists.passportExpiry')} extra={expiryExtra}
          rules={[required, ...expiryRules]}>
          <DatePicker format={DATE_FORMAT} style={{ width: '100%' }} />
        </Form.Item>
      </Col>
      {children}
    </Row>
  )
}
