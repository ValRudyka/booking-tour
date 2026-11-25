import { UploadOutlined } from '@ant-design/icons'
import { Alert, App, Button, Checkbox, Form, Input, Modal, Select, Skeleton, Typography, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { requestCancellation, useCancelRequestForm } from '../../api/cabinet'
import type { CancelReason, OrderDetail, OrderDetailWithPrice, UploadLimits } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { cancelReasonLabel, CANCEL_REASONS, keysOf } from '../../constants/orderLabels'
import { serverText } from '../../features/booking/bookingErrors'
import { acceptOf, fileProblem, typesText } from '../../utils/fileRules'

interface Props {
  order: OrderDetailWithPrice
  open: boolean
  onClose: () => void
  onDone: (order: OrderDetail) => void
}

interface Values {
  reason?: CancelReason
  details?: string
  accept?: boolean
}

/**
 * «Клопотання на скасування бронювання» (ТЗ 4.5.5, form 4.6.1.3). The file limits come from the
 * API (GET /orders/{id}/cancel-request); the ФПВ text is general: the amount is decided by the
 * finance controller when the request is processed, and shown on the order once it is set.
 */
export function CancelRequestDialog({ order, open, onClose, onDone }: Props) {
  const { t } = useTranslation()
  const rules = useCancelRequestForm(order.id, open)
  return (
    <Modal open={open} onCancel={onClose} footer={null} destroyOnHidden width={600}
      title={t('cabinet.cancelRequest.title')}>
      {rules.data ? (
        <RequestForm order={order} limits={rules.data.evidence} maxDetails={rules.data.max_details}
          onClose={onClose} onDone={onDone} />
      ) : rules.isError ? (
        <ApiErrorState error={rules.error} onRetry={() => void rules.refetch()} title={t('cabinet.cancelRequest.title')} />
      ) : <Skeleton active={false} paragraph={{ rows: 5 }} />}
    </Modal>
  )
}

function RequestForm({ order, limits, maxDetails, onClose, onDone }: Omit<Props, 'open'> & {
  limits: UploadLimits
  maxDetails: number
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<Values>()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const lock = useRef(false)   // one request at a time: a second POST would be refused anyway

  const submit = async (values: Values) => {
    if (lock.current || !values.reason) return
    lock.current = true
    setSending(true)
    setError(null)
    try {
      const updated = await requestCancellation(order.id, {
        reason: values.reason, details: values.details ?? '',
        files: files.map((f) => f.originFileObj).filter((f): f is NonNullable<typeof f> => !!f),
      })
      void message.success(t('cabinet.cancelRequest.done'))
      onDone(updated)
    } catch (caught) {
      setError(serverText(caught))   // e.g. a file the server refused by its contents
    } finally {
      lock.current = false
      setSending(false)
    }
  }

  return (
    <Form<Values> form={form} layout="vertical" onFinish={submit}>
      <Typography.Paragraph>{t('cabinet.cancelRequest.intro')}</Typography.Paragraph>
      <Form.Item label={t('cabinet.cancelRequest.number')}>
        <Input value={order.number} readOnly />
      </Form.Item>
      <Form.Item name="reason" label={t('cabinet.cancelRequest.reason')}
        rules={[{ required: true, message: t('cabinet.cancelRequest.reasonRequired') }]}>
        <Select placeholder={t('cabinet.cancelRequest.reason')}
          options={keysOf(CANCEL_REASONS).map((reason) => ({ value: reason, label: cancelReasonLabel(t, reason) }))} />
      </Form.Item>
      <Form.Item name="details" label={t('cabinet.cancelRequest.details')}>
        <Input.TextArea rows={3} maxLength={maxDetails} showCount />
      </Form.Item>
      <Form.Item label={t('cabinet.cancelRequest.files')}
        extra={t('cabinet.cancelRequest.filesHint', { count: limits.max_files, types: typesText(limits), mb: limits.max_file_mb })}
        validateStatus={fileError ? 'error' : undefined} help={fileError ?? undefined}>
        <Upload accept={acceptOf(limits)} multiple fileList={files}
          beforeUpload={(file, batch) => {
            // Several files chosen at once arrive in one batch: count the ones before this one.
            const problem = files.length + batch.indexOf(file) >= limits.max_files
              ? t('cabinet.files.tooMany', { count: limits.max_files })
              : fileProblem(t, file, limits)
            setFileError(problem)
            if (!problem) {
              setFiles((list) => list.length >= limits.max_files ? list
                : [...list, { uid: file.uid, name: file.name, status: 'done', originFileObj: file }])
            }
            return false   // sent with the form, not uploaded on its own
          }}
          onRemove={(file) => {
            setFiles((list) => list.filter((f) => f.uid !== file.uid))
            setFileError(null)
          }}>
          <Button icon={<UploadOutlined aria-hidden />} disabled={files.length >= limits.max_files}>
            {t('cabinet.cancelRequest.addFile')}
          </Button>
        </Upload>
      </Form.Item>
      <Alert type="info" showIcon className="cancel-policy" title={t('cabinet.cancelRequest.policyTitle')}
        description={t('cabinet.cancelRequest.policyText')} />
      <Form.Item name="accept" valuePropName="checked" className="cancel-accept" rules={[{
        validator: (_, value) => value ? Promise.resolve()
          : Promise.reject(new Error(t('cabinet.cancelRequest.acceptRequired'))),
      }]}>
        <Checkbox>{t('cabinet.cancelRequest.accept')}</Checkbox>
      </Form.Item>
      {error && <Alert type="error" showIcon title={error} className="cancel-error" />}
      <div className="cancel-buttons">
        <Button onClick={onClose}>{t('cabinet.cancelRequest.close')}</Button>
        <Button type="primary" danger htmlType="submit" loading={sending}>{t('cabinet.cancelRequest.submit')}</Button>
      </div>
    </Form>
  )
}
