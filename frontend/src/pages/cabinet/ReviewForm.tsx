import { PlusOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Form, Input, Radio, Rate, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { cloneElement, isValidElement, useId, useRef, useState, type ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { createReview, orderKeys, resubmitReview, type ReviewInput } from '../../api/cabinet'
import type { MyReview, NameDisplay, OrderReview } from '../../api/types'
import { keysOf, NAME_DISPLAYS } from '../../constants/orderLabels'
import { useAuth } from '../../features/auth/useAuth'
import { serverText } from '../../features/booking/bookingErrors'
import { acceptOf, fileProblem, typesText } from '../../utils/fileRules'

interface Props {
  orderId: number
  state: OrderReview
  /** The rejected review being corrected (its one resubmission), or null for a new review. */
  existing: MyReview | null
  onCancel?: () => void
  onDone: () => void
}

interface Values {
  hotelRating: number
  serviceRating: number
  positive?: string
  negative?: string
  nameDisplay: NameDisplay
  photosMode: 'keep' | 'replace'
}

/** A browser preview of a chosen photo (jsdom in tests has no object URLs). */
function previewOf(file: File): string | undefined {
  return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : undefined
}

/**
 * Form 4.6.1.4: two required ratings, two optional texts, photos and how the name is shown.
 * Limits (photo count, size, formats, text length) and premoderation come from the API.
 */
export function ReviewForm({ orderId, state, existing, onCancel, onDone }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [form] = Form.useForm<Values>()
  const [photos, setPhotos] = useState<UploadFile[]>([])
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const lock = useRef(false)
  const limits = state.photos
  const hadPhotos = (existing?.photos.length ?? 0) > 0
  const photosMode = Form.useWatch('photosMode', form) ?? 'keep'
  const uploading = !hadPhotos || photosMode === 'replace'
  const nameDisplay: NameDisplay = Form.useWatch('nameDisplay', form) ?? existing?.name_display ?? 'short'

  const submit = async (values: Values) => {
    if (lock.current) return
    lock.current = true
    setSending(true)
    setError(null)
    const input: ReviewInput = {
      hotelRating: values.hotelRating, serviceRating: values.serviceRating,
      positive: values.positive ?? '', negative: values.negative ?? '', nameDisplay: values.nameDisplay,
    }
    const files = photos.map((p) => p.originFileObj).filter((f): f is NonNullable<typeof f> => !!f)
    try {
      const review = existing
        ? await resubmitReview(existing.id, input, files, hadPhotos ? values.photosMode === 'replace' : files.length > 0)
        : await createReview(orderId, input, files)
      queryClient.setQueryData<OrderReview>(orderKeys.review(orderId), (old) => old && { ...old, can_write: false, review })
      void queryClient.invalidateQueries({ queryKey: ['order', orderId] })   // its actions changed
      void queryClient.invalidateQueries({ queryKey: orderKeys.list })
      void message.success(t('review.sent'))
      onDone()
    } catch (caught) {
      setError(serverText(caught))   // e.g. a photo the server refused by its contents
    } finally {
      lock.current = false
      setSending(false)
    }
  }

  return (
    <Card>
      <Form<Values> form={form} layout="vertical" onFinish={submit} initialValues={{
        hotelRating: existing?.hotel_rating ?? 0, serviceRating: existing?.service_rating ?? 0,
        positive: existing?.positive ?? '', negative: existing?.negative ?? '',
        nameDisplay: existing?.name_display ?? 'short', photosMode: 'keep',
      }}>
        <Alert type="info" showIcon className="cancel-policy"
          title={state.premoderation ? t('review.premoderation') : t('review.noPremoderation')} />
        {existing && <Alert type="warning" showIcon className="cancel-policy" title={t('review.resubmitWarning')} />}

        <RatingItem name="hotelRating" label={t('review.hotelRating')} />
        <RatingItem name="serviceRating" label={t('review.serviceRating')} extra={t('review.serviceHint')} />
        <Form.Item name="positive" label={t('review.positive')}>
          <Input.TextArea rows={3} maxLength={state.max_text} showCount placeholder={t('review.positivePlaceholder')} />
        </Form.Item>
        <Form.Item name="negative" label={t('review.negative')}>
          <Input.TextArea rows={3} maxLength={state.max_text} showCount placeholder={t('review.negativePlaceholder')} />
        </Form.Item>

        {hadPhotos && (
          <Form.Item name="photosMode" label={t('review.photosMode')}>
            <Radio.Group options={[
              { value: 'keep', label: t('review.keepPhotos') },
              { value: 'replace', label: t('review.replacePhotos') },
            ]} />
          </Form.Item>
        )}
        {uploading && (
          <Form.Item label={t('review.photos')}
            extra={t('review.photosHint', { count: limits.max_files, types: typesText(limits), mb: limits.max_file_mb })}
            validateStatus={photoError ? 'error' : undefined} help={photoError ?? undefined}>
            <Upload listType="picture-card" accept={acceptOf(limits)} multiple fileList={photos}
              showUploadList={{ showPreviewIcon: false }}
              previewFile={(file) => Promise.resolve(previewOf(file as File) ?? '')}
              beforeUpload={(file, batch) => {
                // Photos beyond the limit are not added (spec 06, §6); the server checks again.
                // Several files chosen at once arrive in one batch: count the ones before this one.
                const problem = photos.length + batch.indexOf(file) >= limits.max_files
                  ? t('cabinet.files.tooMany', { count: limits.max_files })
                  : fileProblem(t, file, limits)
                setPhotoError(problem)
                if (!problem) {
                  setPhotos((list) => list.length >= limits.max_files ? list : [...list, {
                    uid: file.uid, name: file.name, status: 'done', originFileObj: file, thumbUrl: previewOf(file),
                  }])
                }
                return false
              }}
              onRemove={(file) => {
                setPhotos((list) => list.filter((p) => p.uid !== file.uid))
                setPhotoError(null)
              }}>
              {photos.length < limits.max_files && (
                <button type="button" className="upload-button">
                  <PlusOutlined aria-hidden />
                  <span>{t('review.addPhoto')}</span>
                </button>
              )}
            </Upload>
          </Form.Item>
        )}

        <Form.Item name="nameDisplay" label={t('review.nameDisplay')}
          extra={t('review.namePreview', { name: previewName(t('review.anonymous'), nameDisplay, user) })}>
          <Radio.Group options={keysOf(NAME_DISPLAYS).map((value) => ({ value, label: t(`nameDisplay.${value}`) }))} />
        </Form.Item>

        {error && <Alert type="error" showIcon title={error} className="cancel-error" />}
        <div className="cancel-buttons">
          {onCancel && <Button onClick={onCancel}>{t('review.cancelEdit')}</Button>}
          <Button type="primary" htmlType="submit" loading={sending}>
            {existing ? t('review.resubmit') : t('review.submit')}
          </Button>
        </div>
      </Form>
    </Card>
  )
}

/** How the name will look (form 4.6.1.4, field 7). Only a preview: after sending, the page
 * shows the server's own `author`. */
function previewName(anonymous: string, display: NameDisplay,
  user: { first_name: string; last_name: string } | null): string {
  if (!user || display === 'anonymous') return anonymous
  return display === 'full' ? `${user.first_name} ${user.last_name}` : `${user.first_name} ${user.last_name.slice(0, 1)}.`
}

/** A required 1–5 rating. antd Rate's stars are radios: each gets a Ukrainian name («4 з 5»),
 * and the group is named by the field label. */
function RatingItem({ name, label, extra }: { name: 'hotelRating' | 'serviceRating'; label: string; extra?: string }) {
  const { t } = useTranslation()
  const labelId = useId()
  return (
    <Form.Item name={name} label={<span id={labelId}>{label}</span>} extra={extra} required
      rules={[{
        validator: (_, value: number) => value >= 1 && value <= 5 ? Promise.resolve()
          : Promise.reject(new Error(t('review.ratingRequired'))),
      }]}>
      <RatingInput labelId={labelId} />
    </Form.Item>
  )
}

/** Form.Item passes value / onChange; the wrapper is the radio group the label names. */
function RatingInput({ labelId, value, onChange }: { labelId: string; value?: number; onChange?: (value: number) => void }) {
  const { t } = useTranslation()
  return (
    <div role="radiogroup" aria-labelledby={labelId}>
      <Rate value={value} onChange={onChange} allowClear={false}
        characterRender={(node, { index = 0 }) => {
          // The star's own element is the <div role="radio"> inside the <li>.
          const star = isValidElement(node) ? (node as ReactElement<{ children?: ReactElement }>).props.children : null
          if (!isValidElement(node) || !isValidElement(star)) return node
          return cloneElement(node as ReactElement<{ children?: ReactElement }>, {},
            cloneElement(star as ReactElement<Record<string, unknown>>, { 'aria-label': t('review.ratingValue', { value: index + 1 }) }))
        }} />
    </div>
  )
}
