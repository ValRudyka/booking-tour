import { App, DatePicker, Form } from 'antd'
import type { Dayjs } from 'dayjs'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { tourApi } from '../../../api/officeTours'
import { FormModal } from '../../../components/office/FormModal'
import type { TourStateLike } from '../../../features/office/tourActions'
import { actionErrorText, type useTourAction } from '../../../features/office/useOfficeAction'
import { kyivTomorrow } from '../../../utils/format'

interface Values { dates?: [Dayjs, Dayjs] | null }

/**
 * «Копіювати» (spec 10): the copy is a new draft with the original's content, program and
 * photos but never its dates, so the dialog asks for the new range first (from tomorrow, Kyiv).
 * The backend names it «Копія — …»; the editor then opens on it.
 */
export function CopyTourModal({ tour, action, onClose }: {
  tour: TourStateLike | null
  action: ReturnType<typeof useTourAction>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<Values>()
  const tomorrow = kyivTomorrow()

  const { clearError } = action
  useEffect(() => { if (tour) clearError() }, [tour, clearError])

  const submit = async ({ dates }: Values) => {
    if (!tour || !dates) return false
    const copy = await action.run('copy', () => tourApi.copy(tour.id, {
      departure_from: dates[0].format('YYYY-MM-DD'), departure_to: dates[1].format('YYYY-MM-DD'),
    }))
    if (!copy) return false
    void message.success(t('office.tours.done.copy'))
    navigate(`/office/tours/${copy.id}/edit`)
    return true
  }

  return (
    <FormModal<Values> open={tour !== null} title={t('office.tours.copy.title', { title: tour?.title_uk ?? '' })}
      okText={t('office.tours.copy.ok')} cancelText={t('office.tours.confirm.cancel')} busy={action.busy === 'copy'}
      warning={t('office.tours.copy.warning')} form={form} onCancel={onClose} onSubmit={submit}
      error={action.error ? actionErrorText(action.error, t('office.forbiddenTitle')) : null}>
      <Form.Item name="dates" label={t('office.tours.copy.dates')} extra={t('office.tours.copy.datesHint')}
        rules={[{ required: true, message: t('office.tours.rule.datesRequired') }]}>
        <DatePicker.RangePicker format="DD.MM.YYYY" className="office-full-width"
          disabledDate={(day) => day.format('YYYY-MM-DD') < tomorrow}
          placeholder={[t('office.filters.from'), t('office.filters.to')]} />
      </Form.Item>
    </FormModal>
  )
}
