import { Alert, Col, DatePicker, Form, InputNumber, Row, Typography } from 'antd'
import dayjs from 'dayjs'
import { useTranslation } from 'react-i18next'
import type { TourDetail } from '../../api/types'
import { MAX_TOURISTS } from '../../features/booking/bookingRules'
import { formatDate } from '../../utils/format'
import { DATE_FORMAT, ISO } from './bookingForm'

interface Props {
  tour: TourDetail
  /** First and last start date the backend accepts: from tomorrow (Kyiv) within the tour's range. */
  firstDate: string
  lastDate: string
  /** Seats this booking may take: free seats of the tour plus the ones this order already holds. */
  available: number
  hasOrder: boolean
}

/** Step 1 (form 4.6.1.2, fields 2–3): start date and the numbers of adults and children. */
export function StepTrip({ tour, firstDate, lastDate, available, hasOrder }: Props) {
  const { t } = useTranslation()
  return (
    <>
      <Form.Item name="date" label={t('checkout.trip.date')}
        extra={t('checkout.trip.dateHint', { from: formatDate(firstDate), to: formatDate(lastDate) })}
        rules={[{ required: true, message: t('checkout.rules.dateRequired') }]}>
        <DatePicker format={DATE_FORMAT} allowClear={false} style={{ width: '100%', maxWidth: 260 }}
          disabledDate={(day) => day.isBefore(dayjs(firstDate, ISO), 'day') || day.isAfter(dayjs(lastDate, ISO), 'day')} />
      </Form.Item>
      <Row gutter={16}>
        <Col xs={24} sm={12}>
          <Form.Item name="adults" label={t('checkout.trip.adults')} dependencies={['children']}
            extra={t('checkout.trip.freeSeats', { count: Math.max(available, 0) })}
            rules={[
              { required: true, message: t('checkout.rules.minAdults') },
              ({ getFieldValue }) => ({
                validator(_, adults: number | null) {
                  if (!adults || adults < 1) return Promise.reject(new Error(t('checkout.rules.minAdults')))
                  const total = adults + (getFieldValue('children') ?? 0)
                  if (total > MAX_TOURISTS) return Promise.reject(new Error(t('checkout.rules.maxTourists', { max: MAX_TOURISTS })))
                  if (total > available) {
                    return Promise.reject(new Error(t('checkout.rules.noSeats', { count: Math.max(available, 0) })))
                  }
                  return Promise.resolve()
                },
              }),
            ]}>
            <InputNumber min={1} precision={0} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item name="children" label={t('checkout.trip.children')}>
            <InputNumber min={0} precision={0} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
      </Row>
      <Typography.Paragraph type="secondary">
        {/* One departure city per tour (form 4.6.2.1): shown, nothing to choose. */}
        {`${t('booking.departure')}: `}
        {tour.transport_type === 'none' || !tour.departure_city ? t('tour.noTransport')
          : t(tour.transport_type === 'bus' ? 'tour.departureBus' : 'tour.departureAir',
            { city: tour.departure_city.name_uk })}
      </Typography.Paragraph>
      {!hasOrder && <Alert type="info" showIcon title={t('checkout.trip.holdNote')} />}
    </>
  )
}
