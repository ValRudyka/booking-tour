import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, StarOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Popconfirm, Space, Tag, Typography, Upload } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { mediaUrl } from '../../../api/client'
import { deleteTourImage, reorderTourImages, uploadTourImages } from '../../../api/officeTours'
import type { ManagerTour, TourRules } from '../../../api/types'
import { actionErrorText, useTourAction } from '../../../features/office/useOfficeAction'
import { acceptOf, fileProblem, typesText } from '../../../utils/fileRules'

/**
 * Step 4 «Фото» (form 4.6.2.1, field 18). Every change is saved at once (upload, delete, order),
 * so photos never count as unsaved changes. The first photo is the main one (catalog card,
 * gallery start): «Зробити головним» moves a photo first, the arrows move it by one (no drag and
 * drop: keyboard friendly). Type, size and count are checked against the API's limits before
 * sending; the server checks again, including the file contents.
 */
export function TourPhotosStep({ tour, rules, editable }: { tour: ManagerTour; rules: TourRules; editable: boolean }) {
  const { t } = useTranslation()
  const action = useTourAction(tour.id)
  const [problems, setProblems] = useState<string[]>([])
  const limits = rules.photos
  const images = tour.images
  const left = limits.max_files - images.length

  // useTourAction refetches the tour after each change (the answers are photos, not the card).
  const upload = async (files: File[]) => {
    const found = files.map((file) => fileProblem(t, file, limits)).filter((p): p is string => p !== null)
    const good = files.filter((file) => fileProblem(t, file, limits) === null)
    if (good.length > left) found.push(t('office.tours.photos.tooMany', { max: limits.max_files, left }))
    setProblems(found)
    if (found.length > 0 || good.length === 0) return
    await action.run('upload', () => uploadTourImages(tour.id, good))
  }

  const reorder = (ids: number[], name: string) => action.run(name, () => reorderTourImages(tour.id, ids))

  const move = (from: number, to: number) => {
    const ids = images.map((image) => image.id)
    const [moved] = ids.splice(from, 1)
    ids.splice(to, 0, moved)
    void reorder(ids, `move-${images[from].id}`)
  }

  const remove = (imageId: number) =>
    action.run(`delete-${imageId}`, async () => { await deleteTourImage(tour.id, imageId); return true })

  const busy = action.busy !== null

  return (
    <Space orientation="vertical" size={16} className="office-full-width">
      <Typography.Paragraph type="secondary">
        {t('office.tours.photos.hint', { types: typesText(limits), mb: limits.max_file_mb, max: limits.max_files })}
      </Typography.Paragraph>
      {editable && (
        <Upload multiple accept={acceptOf(limits)} showUploadList={false} disabled={busy || left <= 0}
          beforeUpload={(file, fileList) => {
            if (file === fileList[0]) void upload(fileList as unknown as File[])
            return Upload.LIST_IGNORE
          }}>
          <Button icon={<UploadOutlined aria-hidden />} loading={action.busy === 'upload'} disabled={busy || left <= 0}>
            {t('office.tours.photos.add')}
          </Button>
        </Upload>
      )}
      {problems.length > 0 && (
        <Alert type="error" showIcon role="alert" title={t('office.tours.photos.refused')}
          description={<ul className="office-plain-list">{problems.map((p) => <li key={p}>{p}</li>)}</ul>} />
      )}
      {action.error && (
        <Alert type="error" showIcon role="alert" closable={{ onClose: action.clearError }}
          title={actionErrorText(action.error, t('office.forbiddenTitle'))} />
      )}
      {images.length === 0 ? (
        <Alert type="info" showIcon role="note" title={t('office.tours.photos.none')} />
      ) : (
        <ol className="office-photo-grid" aria-label={t('office.tours.photos.list')}>
          {images.map((image, index) => {
            const n = index + 1
            return (
              <li key={image.id}>
                <Card size="small" cover={<img src={mediaUrl(image.url) ?? undefined} alt={t('office.tours.photos.alt', { n })} className="office-photo" />}>
                  <Space orientation="vertical" size={8} className="office-full-width">
                    {index === 0 ? <Tag color="success">{t('office.tours.photos.main')}</Tag>
                      : <Typography.Text type="secondary">{t('office.tours.photos.number', { n })}</Typography.Text>}
                    {editable && (
                      <Space wrap size={4}>
                        {index > 0 && (
                          <Button size="small" icon={<StarOutlined aria-hidden />} disabled={busy}
                            onClick={() => move(index, 0)}>{t('office.tours.photos.makeMain')}</Button>
                        )}
                        <Button size="small" icon={<ArrowUpOutlined aria-hidden />} disabled={busy || index === 0}
                          onClick={() => move(index, index - 1)} aria-label={t('office.tours.photos.up', { n })} />
                        <Button size="small" icon={<ArrowDownOutlined aria-hidden />} disabled={busy || index === images.length - 1}
                          onClick={() => move(index, index + 1)} aria-label={t('office.tours.photos.down', { n })} />
                        <Popconfirm title={t('office.tours.photos.deleteConfirm', { n })} okText={t('office.tours.photos.delete')}
                          cancelText={t('office.tours.confirm.cancel')} okButtonProps={{ danger: true }} onConfirm={() => remove(image.id)}>
                          <Button size="small" danger icon={<DeleteOutlined aria-hidden />} disabled={busy}
                            loading={action.busy === `delete-${image.id}`} aria-label={t('office.tours.photos.deleteLabel', { n })} />
                        </Popconfirm>
                      </Space>
                    )}
                  </Space>
                </Card>
              </li>
            )
          })}
        </ol>
      )}
    </Space>
  )
}
