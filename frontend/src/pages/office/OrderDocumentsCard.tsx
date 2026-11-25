import { DeleteOutlined, DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Form, Popconfirm, Select, Space, Typography, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteDocument, fetchOfficeDocument, uploadDocuments, useDocumentRules } from '../../api/office'
import type { DocumentRules, ManagerOrder, OrderDocumentType, StaffOrderDocument, UploadLimits } from '../../api/types'
import { documentLabel } from '../../constants/orderLabels'
import { actionErrorText, useOfficeAction } from '../../features/office/useOfficeAction'
import { fallbackFilename, filenameFromDisposition, saveBlob } from '../../utils/download'
import { acceptOf, fileProblem, typesText } from '../../utils/fileRules'
import { formatKyivDateTime } from '../../utils/format'
import { findAction } from '../../features/office/staffActions'

type Action = ReturnType<typeof useOfficeAction>

/**
 * «Документи» (spec 09 §3, form 4.6.2.2 field 5): every file of the order, the client's
 * cancellation evidence included. Files are private, so they are fetched with the token
 * (utils/download.ts). Delete is offered where the API says `can_delete`; upload where
 * staff_actions lists `upload_documents` (types, count, size and formats from the API).
 */
export function OrderDocumentsCard({ order }: { order: ManagerOrder }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const action = useOfficeAction(order.id)       // its errors show in this card
  const upload = findAction(order, 'upload_documents')
  const [downloadError, setDownloadError] = useState<string | null>(null)

  const download = async (doc: StaffOrderDocument) => {
    setDownloadError(null)
    try {
      const { blob, disposition } = await fetchOfficeDocument(order.id, doc.id)
      saveBlob(blob, filenameFromDisposition(disposition) ?? fallbackFilename(`${doc.doc_type}-${order.number}-${doc.id}`, blob))
    } catch {
      setDownloadError(t('office.order.downloadFailed'))
    }
  }

  const remove = async (doc: StaffOrderDocument) => {
    const result = await action.run(`delete-${doc.id}`, async () => {
      await deleteDocument(order.id, doc.id)
      return true
    })
    if (result) message.success(t('office.order.actionDone.deleteDocument'))
  }

  return (
    <Card title={<h2 className="office-card-title">{t('office.order.documentsTitle')}</h2>}>
      {downloadError && <Alert type="error" showIcon role="alert" title={downloadError} className="office-block" />}
      {action.error && (
        <Alert type="error" showIcon role="alert" className="office-block" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
      )}
      {order.documents.length === 0 ? (
        <Typography.Paragraph type="secondary">{t('office.order.noDocuments')}</Typography.Paragraph>
      ) : (
        <ul className="office-doc-list">
          {order.documents.map((doc) => {
            const name = documentLabel(t, doc.doc_type)
            return (
              <li key={doc.id}>
                <Space orientation="vertical" size={0}>
                  <Typography.Text strong>{name}</Typography.Text>
                  <Typography.Text type="secondary">
                    {t('office.order.uploadedAt', { date: formatKyivDateTime(doc.uploaded_at) })}
                  </Typography.Text>
                </Space>
                <Space>
                  <Button icon={<DownloadOutlined aria-hidden />} onClick={() => void download(doc)}
                    aria-label={t('office.order.downloadNamed', { name })}>
                    {t('office.order.download')}
                  </Button>
                  {doc.can_delete && (
                    <Popconfirm title={t('office.order.deleteConfirm')} description={t('office.order.deleteWarning')}
                      okText={t('office.order.deleteOk')} okButtonProps={{ danger: true }} cancelText={t('office.order.cancel')}
                      onConfirm={() => remove(doc)} disabled={action.busy !== null}>
                      <Button danger icon={<DeleteOutlined aria-hidden />} disabled={action.busy !== null}
                        loading={action.busy === `delete-${doc.id}`} aria-label={t('office.order.deleteNamed', { name })}>
                        {t('office.order.deleteDocument')}
                      </Button>
                    </Popconfirm>
                  )}
                </Space>
              </li>
            )
          })}
        </ul>
      )}
      {upload && (upload.allowed
        ? <UploadForm order={order} action={action} />
        : upload.reason && <Typography.Text className="office-reason">{upload.reason}</Typography.Text>)}
    </Card>
  )
}

function UploadForm({ order, action }: { order: ManagerOrder; action: Action }) {
  const { t } = useTranslation()
  const rules = useDocumentRules(true)
  if (rules.isError) return <Alert type="error" showIcon title={t('office.order.upload.rulesFailed')} />
  if (!rules.data) return null
  return <UploadFields order={order} action={action} rules={rules.data} />
}

function UploadFields({ order, action, rules }: { order: ManagerOrder; action: Action; rules: DocumentRules }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<{ doc_type: OrderDocumentType }>()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [fileError, setFileError] = useState<string | null>(null)
  const left = Math.max(0, rules.max_documents - order.documents.length)
  const limits: UploadLimits = { max_files: left, max_file_mb: rules.max_file_mb, file_types: rules.file_types }

  const submit = async ({ doc_type }: { doc_type: OrderDocumentType }) => {
    if (files.length === 0) {
      setFileError(t('office.order.upload.filesRequired'))
      return
    }
    const result = await action.run('upload',
      () => uploadDocuments(order.id, doc_type, files.map((f) => f.originFileObj as File)))
    if (result) {
      setFiles([])
      form.resetFields()
      message.success(t('office.order.actionDone.upload'))
    }
  }
  return (
    <Form form={form} layout="vertical" className="office-upload" onFinish={(values) => void submit(values)}
      aria-label={t('office.order.upload.title')}>
      <Typography.Title level={3} className="office-card-subtitle">{t('office.order.upload.title')}</Typography.Title>
      <Form.Item name="doc_type" label={t('office.order.upload.type')}
        rules={[{ required: true, message: t('office.order.upload.typeRequired') }]}>
        <Select options={rules.doc_types.map((type) => ({ value: type, label: documentLabel(t, type) }))} />
      </Form.Item>
      <Form.Item label={t('office.order.upload.files')}
        extra={t('office.order.upload.hint', { types: typesText(limits), mb: limits.max_file_mb, left })}
        validateStatus={fileError ? 'error' : undefined} help={fileError ?? undefined}>
        <Upload accept={acceptOf(limits)} multiple fileList={files}
          beforeUpload={(file, batch) => {
            const problem = files.length + batch.indexOf(file) >= left
              ? t('cabinet.files.tooMany', { count: left })
              : fileProblem(t, file, limits)
            setFileError(problem)
            if (!problem) {
              setFiles((list) => list.length >= left ? list
                : [...list, { uid: file.uid, name: file.name, status: 'done', originFileObj: file }])
            }
            return false   // sent with the form, not uploaded on its own
          }}
          onRemove={(file) => {
            setFiles((list) => list.filter((f) => f.uid !== file.uid))
            setFileError(null)
          }}>
          <Button icon={<UploadOutlined aria-hidden />}>{t('office.order.upload.choose')}</Button>
        </Upload>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={action.busy === 'upload'} disabled={action.busy !== null}>
        {t('office.order.upload.submit')}
      </Button>
    </Form>
  )
}
