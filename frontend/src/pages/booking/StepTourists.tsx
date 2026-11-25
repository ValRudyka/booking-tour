import { Alert, Button, Card, Col, DatePicker, Form, Input, Row, Select, Typography, type FormInstance } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SavedPassport, User } from '../../api/types'
import {
  ageOn, CHILD_AGE_LIMIT, cleanPassportNumber, isLatinPassportName, isPassportNumber, passportValidUntil,
} from '../../features/booking/bookingRules'
import type { TouristField } from '../../features/booking/bookingErrors'
import { formatDate } from '../../utils/format'
import { DATE_FORMAT, ISO, type BookingValues } from './bookingForm'

interface Props {
  form: FormInstance<BookingValues>
  adults: number
  startDate: string
  endDate: string
  user: User
  passports: SavedPassport[]
  /** After a reload: the numbers were never stored in the browser and must be typed again. */
  reenterNumbers: boolean
}

/** Step 2 (form 4.6.1.2, fields 3.1–3.6): one block per tourist, «Дорослий 1…», «Дитина 1…». */
export function StepTourists({ form, adults, startDate, endDate, user, passports, reenterNumbers }: Props) {
  const { t } = useTranslation()
  const validUntil = passportValidUntil(endDate)
  return (
    <>
      {reenterNumbers && <Alert type="info" showIcon className="booking-block" title={t('checkout.tourists.reenterNumbers')} />}
      <Form.List name="tourists">
        {(fields) => fields.map((field, index) => {
          const isAdult = index < adults
          const n = isAdult ? index + 1 : index - adults + 1
          return (
            <TouristCard key={field.key} form={form} index={index} isAdult={isAdult}
              title={t(isAdult ? 'checkout.tourists.adult' : 'checkout.tourists.child', { n })}
              startDate={startDate} validUntil={validUntil} user={index === 0 ? user : null}
              passports={passports} />
          )
        })}
      </Form.List>
    </>
  )
}

interface CardProps {
  form: FormInstance<BookingValues>
  index: number
  isAdult: boolean
  title: string
  startDate: string
  validUntil: string
  /** Only for the first tourist: «Заповнити з мого профілю». */
  user: User | null
  passports: SavedPassport[]
}

function TouristCard({ form, index, isAdult, title, startDate, validUntil, user, passports }: CardProps) {
  const { t } = useTranslation()
  const headingId = useId()
  const passportSelectId = useId()
  const [profileNote, setProfileNote] = useState(false)
  const name = (field: TouristField) => ['tourists', index, field] as ['tourists', number, TouristField]
  const start = formatDate(startDate)

  // The profile has the birth date and the names; the names are Ukrainian for Ukrainian citizens
  // (ТЗ 4.5.1), so they are copied only when they are already in Latin letters.
  const latinProfile = !!user && isLatinPassportName(user.last_name) && isLatinPassportName(user.first_name)
  const fillFromProfile = () => {
    if (!user) return
    if (user.birth_date) form.setFieldValue(name('birth_date'), dayjs(user.birth_date, ISO))
    if (latinProfile) {
      form.setFieldValue(name('last_name_lat'), user.last_name)
      form.setFieldValue(name('first_name_lat'), user.first_name)
    }
    setProfileNote(!latinProfile)
  }
  // A saved passport has names, number and expiry, but no birth date (backend PassportOut).
  const fillFromPassport = (id: number) => {
    const passport = passports.find((p) => p.id === id)
    if (!passport) return
    form.setFieldValue(name('last_name_lat'), passport.last_name_lat)
    form.setFieldValue(name('first_name_lat'), passport.first_name_lat)
    form.setFieldValue(name('passport_number'), passport.passport_number)
    form.setFieldValue(name('passport_expiry'), dayjs(passport.expiry_date, ISO))
    void form.validateFields([name('last_name_lat'), name('first_name_lat'), name('passport_number'),
      name('passport_expiry')]).catch(() => undefined)
  }

  const required = { required: true, message: t('checkout.rules.required') }
  const latin = {
    validator: (_: unknown, value?: string) => (!value || isLatinPassportName(value) ? Promise.resolve()
      : Promise.reject(new Error(t('checkout.rules.latin')))),
  }

  return (
    <Card className="booking-tourist" aria-labelledby={headingId} size="small"
      title={<h3 id={headingId} className="booking-tourist-title">{title}</h3>}>
      <Typography.Paragraph type="secondary">
        {t(isAdult ? 'checkout.tourists.adultHint' : 'checkout.tourists.childHint', { date: start })}
      </Typography.Paragraph>
      {(user && (user.birth_date || latinProfile)) || passports.length > 0 ? (
        <div className="booking-autofill">
          {user && (user.birth_date || latinProfile) && (
            <Button onClick={fillFromProfile}>{t('checkout.tourists.fromProfile')}</Button>
          )}
          {passports.length > 0 && (
            <div className="booking-autofill-select">
              <label htmlFor={passportSelectId}>{t('checkout.tourists.savedPassport')}</label>
              <Select id={passportSelectId} value={null} style={{ minWidth: 240 }}
                placeholder={t('checkout.tourists.savedPassportPlaceholder')} onChange={fillFromPassport}
                options={passports.map((p) => ({
                  value: p.id,
                  label: t('checkout.tourists.savedPassportOption',
                    { name: `${p.last_name_lat} ${p.first_name_lat}`, number: p.passport_number }),
                }))} />
            </div>
          )}
        </div>
      ) : null}
      {profileNote && <Alert type="info" showIcon className="booking-block" title={t('checkout.tourists.fromProfileNote')} />}
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Form.Item name={[index, 'last_name_lat']} label={t('checkout.tourists.lastName')}
            extra={t('checkout.tourists.nameHint')} rules={[required, latin]}>
            <Input autoComplete="family-name" maxLength={100} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name={[index, 'first_name_lat']} label={t('checkout.tourists.firstName')} rules={[required, latin]}>
            <Input autoComplete="given-name" maxLength={100} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name={[index, 'birth_date']} label={t('checkout.tourists.birthDate')} rules={[required, {
            validator: (_, value?: Dayjs | null) => {
              if (!value) return Promise.resolve()
              const birth = value.format(ISO)
              if (birth > startDate) return Promise.reject(new Error(t('checkout.rules.birthAfterStart')))
              const child = ageOn(birth, startDate) < CHILD_AGE_LIMIT
              if (isAdult && child) return Promise.reject(new Error(t('checkout.rules.adultAge', { date: start })))
              if (!isAdult && !child) return Promise.reject(new Error(t('checkout.rules.childAge', { date: start })))
              return Promise.resolve()
            },
          }]}>
            <DatePicker format={DATE_FORMAT} style={{ width: '100%' }}
              disabledDate={(day) => day.isAfter(dayjs(startDate, ISO), 'day')} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name={[index, 'passport_number']} label={t('checkout.tourists.passportNumber')}
            normalize={(value?: string) => (value ? cleanPassportNumber(value) : value)}
            rules={[required, {
              validator: (_, value?: string) => (!value || isPassportNumber(value) ? Promise.resolve()
                : Promise.reject(new Error(t('checkout.rules.passportNumber')))),
            }]}>
            <Input autoComplete="off" maxLength={20} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name={[index, 'passport_expiry']} label={t('checkout.tourists.passportExpiry')}
            extra={t('checkout.tourists.expiryHint', { date: formatDate(validUntil) })}
            rules={[required, {
              validator: (_, value?: Dayjs | null) => (!value || value.format(ISO) >= validUntil ? Promise.resolve()
                : Promise.reject(new Error(t('checkout.rules.passportExpiry', { date: formatDate(validUntil) })))),
            }]}>
            <DatePicker format={DATE_FORMAT} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
    </Card>
  )
}
