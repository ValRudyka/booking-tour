import { DownloadOutlined, FileOutlined } from '@ant-design/icons'
import { Alert, Button, Card, List, Skeleton, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchDocument, useOrderDocuments } from '../../api/cabinet'
import type { OrderDetailWithPrice, OrderDocument } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { documentLabel } from '../../constants/orderLabels'
import { serverText } from '../../features/booking/bookingErrors'
import { formatKyivDateTime } from '../../utils/format'
import { fallbackFilename, filenameFromDisposition, saveBlob } from '../../utils/download'
import { has } from './cabinetPaths'

/**
 * Trip documents (ТЗ 4.5.4 step 5). They are private files: «Завантажити» makes an authorised
 * request (the token is sent by the API client) and saves the Blob, a plain link would be refused.
 * Shown when the API allows it (`download_documents`); before that, while the booking is still
 * being processed (`cancel_request` is allowed), a note says when they come.
 */
export function OrderDocuments({ order }: { order: OrderDetailWithPrice }) {
  const { t } = useTranslation()
  const visible = has(order, 'download_documents')
  const documents = useOrderDocuments(order.id, visible)
  const title = <h2 className="cabinet-section-title">{t('cabinet.documents.title')}</h2>

  if (!visible) {
    if (!has(order, 'cancel_request')) return null
    return (
      <Card className="order-section" title={title}>
        <Typography.Text type="secondary">{t('cabinet.documents.pending')}</Typography.Text>
      </Card>
    )
  }
  return (
    <Card className="order-section" title={title}>
      {documents.isError ? (
        <ApiErrorState error={documents.error} onRetry={() => void documents.refetch()} title={t('cabinet.documents.title')} />
      ) : !documents.data ? (
        <Skeleton active={false} paragraph={{ rows: 2 }} />
      ) : documents.data.length === 0 ? (
        <Typography.Text type="secondary">{t('cabinet.documents.preparing')}</Typography.Text>
      ) : (
        <List dataSource={documents.data} rowKey="id"
          renderItem={(doc) => <DocumentRow orderId={order.id} orderNumber={order.number} doc={doc} />} />
      )}
    </Card>
  )
}

function DocumentRow({ orderId, orderNumber, doc }: { orderId: number; orderNumber: string; doc: OrderDocument }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const name = documentLabel(t, doc.doc_type)
  const download = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const { blob, disposition } = await fetchDocument(orderId, doc.id)
      saveBlob(blob, filenameFromDisposition(disposition) ?? fallbackFilename(`${doc.doc_type}-${orderNumber}-${doc.id}`, blob))
    } catch (caught) {
      setError(serverText(caught))
    } finally {
      setBusy(false)
    }
  }
  return (
    <List.Item actions={[
      <Button key="download" icon={<DownloadOutlined aria-hidden />} loading={busy} onClick={download}
        aria-label={t('cabinet.documents.downloadOf', { name })}>
        {t('cabinet.documents.download')}
      </Button>,
    ]}>
      <List.Item.Meta avatar={<FileOutlined aria-hidden />} title={name}
        description={<>
          {t('cabinet.documents.uploaded', { date: formatKyivDateTime(doc.uploaded_at) })}
          {error && <Alert type="error" showIcon title={error} className="document-error" />}
        </>} />
    </List.Item>
  )
}
