import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { App, Alert, Button, Card, Col, Empty, Form, Input, List, Modal, Popconfirm, Skeleton, Space, Tag, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../api/client'
import { useSavedPassports } from '../../api/orders'
import { deletePassport, PASSPORTS_KEY, savePassport } from '../../api/passports'
import type { SavedPassport } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import {
  EARLIEST_BIRTH_DATE, expiryState, isAuthorityCode, MAX_SAVED_PASSPORTS,
} from '../../features/booking/bookingRules'
import { PassportFields } from '../../features/booking/PassportFields'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDate, kyivToday, maskPassport } from '../../utils/format'
import './CabinetPages.css'

const ISO = 'YYYY-MM-DD'

interface PassportValues {
  last_name_lat: string
  first_name_lat: string
  birth_date: Dayjs | null
  passport_number: string
  expiry_date: Dayjs | null
  issuing_authority?: string
}

const FORM_FIELDS = ['last_name_lat', 'first_name_lat', 'birth_date', 'passport_number', 'expiry_date',
  'issuing_authority'] as const

/** /cabinet/tourists (spec 08 §3, form 4.6.1.1, field 8): passports for the booking autofill. */
export function TouristsPage() {
  const { t } = useTranslation()
  const title = t('cabinet.tourists.title')
  useDocumentTitle(title)
  const passports = useSavedPassports()
  // undefined = closed, null = a new tourist, else the one being edited.
  const [editing, setEditing] = useState<SavedPassport | null | undefined>(undefined)
  const list = passports.data ?? []
  const full = list.length >= MAX_SAVED_PASSPORTS

  const addButton = (
    <Button type="primary" icon={<PlusOutlined aria-hidden />} onClick={() => setEditing(null)} disabled={full}>
      {t('cabinet.tourists.add')}
    </Button>
  )

  return (
    <section aria-labelledby="tourists-title">
      <h1 id="tourists-title" className="cabinet-title">{title}</h1>
      {passports.isPending ? (
        <Skeleton active={false} paragraph={{ rows: 4 }} />
      ) : passports.isError ? (
        <ApiErrorState error={passports.error} onRetry={() => void passports.refetch()} title={title} />
      ) : list.length === 0 ? (
        <Card>
          <Empty description={
            <Space orientation="vertical" size={4}>
              <Typography.Text strong>{t('cabinet.tourists.emptyTitle')}</Typography.Text>
              <Typography.Text>{t('cabinet.tourists.emptyText')}</Typography.Text>
            </Space>
          }>
            {addButton}
          </Empty>
        </Card>
      ) : (
        <>
          <Typography.Paragraph type="secondary">{t('cabinet.tourists.intro')}</Typography.Paragraph>
          <Space wrap className="tourists-toolbar">
            {addButton}
            {full && <Typography.Text type="secondary">{t('cabinet.tourists.limit', { max: MAX_SAVED_PASSPORTS })}</Typography.Text>}
          </Space>
          <List className="tourists-list" dataSource={list} rowKey="id"
            renderItem={(passport) => <TouristItem passport={passport} onEdit={() => setEditing(passport)} />} />
        </>
      )}
      {editing !== undefined && <TouristDialog passport={editing} onClose={() => setEditing(undefined)} />}
    </section>
  )
}

function TouristItem({ passport, onEdit }: { passport: SavedPassport; onEdit: () => void }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState(false)
  const name = `${passport.last_name_lat} ${passport.first_name_lat}`
  const expiry = expiryState(passport.expiry_date, kyivToday())

  const remove = async () => {
    setDeleting(true)
    try {
      await deletePassport(passport.id)
      await queryClient.invalidateQueries({ queryKey: PASSPORTS_KEY })
      void message.success(t('cabinet.tourists.deleted'))
    } catch (error) {
      void message.error(error instanceof ApiError ? error.message : t('errors.generic'))
      setDeleting(false)
    }
  }

  return (
    <List.Item actions={[
      <Button key="edit" icon={<EditOutlined aria-hidden />} onClick={onEdit}
        aria-label={t('cabinet.tourists.editOf', { name })}>{t('cabinet.tourists.edit')}</Button>,
      <Popconfirm key="delete" title={t('cabinet.tourists.deleteConfirm', { name })}
        okText={t('cabinet.tourists.delete')} cancelText={t('cabinet.tourists.keep')} okButtonProps={{ danger: true }}
        onConfirm={remove}>
        <Button danger icon={<DeleteOutlined aria-hidden />} loading={deleting}
          aria-label={t('cabinet.tourists.deleteOf', { name })}>{t('cabinet.tourists.delete')}</Button>
      </Popconfirm>,
    ]}>
      {/* Not List.Item.Meta: it wraps the title in an h4, and the name is an h2 under the page's h1. */}
      <div>
        <h2 className="cabinet-section-title tourist-name">{name}</h2>
        <dl className="order-card-facts">
          <dt>{t('checkout.tourists.birthDate')}</dt>
          <dd>{passport.birth_date ? formatDate(passport.birth_date) : t('cabinet.tourists.birthMissing')}</dd>
          <dt>{t('cabinet.tourists.passport')}</dt>
          <dd>{maskPassport(passport.passport_number)}</dd>
          <dt>{t('checkout.tourists.passportExpiry')}</dt>
          <dd>
            <Space size={8} wrap>
              {formatDate(passport.expiry_date)}
              {expiry === 'soon' && <Tag color="warning">{t('cabinet.tourists.expiresSoon')}</Tag>}
              {expiry === 'expired' && <Tag color="error">{t('cabinet.tourists.expired')}</Tag>}
            </Space>
          </dd>
        </dl>
      </div>
    </List.Item>
  )
}

function toValues(passport: SavedPassport | null): Partial<PassportValues> {
  if (!passport) return {}
  return {
    last_name_lat: passport.last_name_lat, first_name_lat: passport.first_name_lat,
    birth_date: passport.birth_date ? dayjs(passport.birth_date, ISO) : null,
    passport_number: passport.passport_number,
    expiry_date: dayjs(passport.expiry_date, ISO), issuing_authority: passport.issuing_authority ?? '',
  }
}

/** Add or edit in a Modal; the same fields and checks as the booking step (PassportFields). */
function TouristDialog({ passport, onClose }: { passport: SavedPassport | null; onClose: () => void }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<PassportValues>()
  const [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState<string | null>(null)
  const today = kyivToday()

  const save = async (values: PassportValues) => {
    setAlert(null)
    setSaving(true)
    try {
      await savePassport({
        last_name_lat: values.last_name_lat, first_name_lat: values.first_name_lat,
        passport_number: values.passport_number, issuing_authority: values.issuing_authority?.trim() || null,
        expiry_date: values.expiry_date!.format(ISO), birth_date: values.birth_date!.format(ISO),
      }, passport?.id)
      await queryClient.invalidateQueries({ queryKey: PASSPORTS_KEY })
      void message.success(t('cabinet.tourists.saved'))
      onClose()
    } catch (error) {
      setSaving(false)
      const fields = error instanceof ApiError ? error.issues.flatMap((issue) => {
        const field = issue.loc[0] === 'body' ? String(issue.loc[1] ?? '') : ''
        if (!(FORM_FIELDS as readonly string[]).includes(field)) return []
        // The backend's own rules speak to the client; pydantic texts are English.
        return [{ name: field as keyof PassportValues,
          errors: [issue.type === 'profile_rule' ? issue.msg : t('checkout.errors.badValue')] }]
      }) : []
      if (fields.length > 0) {
        form.setFields(fields)
        return
      }
      // A plain text: the limit of 20, a missing passport (404), maintenance.
      setAlert(error instanceof ApiError && error.detail ? error.detail
        : error instanceof ApiError ? error.message : t('errors.generic'))
    }
  }

  return (
    <Modal open title={t(passport ? 'cabinet.tourists.editTitle' : 'cabinet.tourists.addTitle')}
      onCancel={onClose} okText={t('cabinet.tourists.save')} cancelText={t('cabinet.profile.cancel')}
      confirmLoading={saving} onOk={() => form.submit()} width={640}>
      <Form form={form} layout="vertical" requiredMark noValidate onFinish={save} initialValues={toValues(passport)}
        scrollToFirstError={{ focus: true, block: 'center' }}>
        <PassportFields name={(field) => (field === 'expiry' ? 'expiry_date' : field)}
          birthMax={today}
          birthRules={[{
            validator: (_, value?: Dayjs | null) => {
              if (!value) return Promise.resolve()
              const birth = value.format(ISO)
              if (birth > today) return Promise.reject(new Error(t('cabinet.tourists.birthFuture')))
              if (birth < EARLIEST_BIRTH_DATE) return Promise.reject(new Error(t('cabinet.tourists.birthCheck')))
              return Promise.resolve()
            },
          }]}
          expiryExtra={t('cabinet.tourists.expiryHint')}
          expiryRules={[{
            validator: (_, value?: Dayjs | null) => (!value || value.format(ISO) > today ? Promise.resolve()
              : Promise.reject(new Error(t('cabinet.tourists.expiryPast')))),
          }]}>
          <Col xs={24} md={12}>
            <Form.Item name="issuing_authority" label={t('cabinet.tourists.authority')}
              extra={t('cabinet.tourists.authorityHint')}
              rules={[{ validator: (_, value?: string) => (!value?.trim() || isAuthorityCode(value)
                ? Promise.resolve() : Promise.reject(new Error(t('cabinet.tourists.authorityFormat')))) }]}>
              <Input inputMode="numeric" maxLength={4} autoComplete="off" />
            </Form.Item>
          </Col>
        </PassportFields>
        {alert && <Alert type="error" showIcon role="alert" title={alert} />}
      </Form>
    </Modal>
  )
}
