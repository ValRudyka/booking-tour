import { PlusOutlined } from '@ant-design/icons'
import {
  Alert, Button, Descriptions, Drawer, Flex, Form, Input, Modal, Select, Space, Spin, Table, Tabs, Tag, Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import type { Rule } from 'antd/es/form'
import type { TFunction } from 'i18next'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { adminKeys, adminUsersApi, useAdminUser, useAdminUsers } from '../../../api/admin'
import { ApiError } from '../../../api/client'
import type { AdminUser, StaffCreated, UserActionInfo, UserAdminAction, UserRole } from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { FilterBar, type FilterField } from '../../../components/office/FilterBar'
import { FormModal } from '../../../components/office/FormModal'
import { ServerActionButton } from '../../../components/office/ServerActionButton'
import { roleLabel } from '../../../constants/orderLabels'
import { useAdminAction } from '../../../features/admin/useAdminAction'
import { emailRules, nameRules, newPasswordRules, repeatRules } from '../../../features/auth/formRules'
import { PasswordRules } from '../../../features/auth/PasswordRules'
import { isValidPhone, normalizePhone } from '../../../features/auth/rules'
import { actionErrorText } from '../../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { formatKyivDateTime } from '../../../utils/format'
import { OfficeForbidden } from '../OfficeHome'
import { useFieldIssues } from './formErrors'
import {
  parseUsers, STAFF_ROLES, USER_TABS, USERS_PAGE_SIZE, usersFilterValues, usersFromFilters, usersQuery, usersSearch,
  type UsersState,
} from './usersParams'
import '../../../layouts/OfficeLayout.css'
import './admin.css'

const KEYS = [adminKeys.users] as const
type Dialog = 'create' | 'edit' | 'role' | 'block' | 'unblock' | 'reset' | null

/**
 * «Користувачі» (spec 13 §1, ТЗ 4.5.8): tabs «Персонал» / «Клієнти», the filter bar, a server
 * table and the user's card in a Drawer (`?user=`). Every action button comes from the user's
 * `user_actions` (backend services/admin_actions.py): a rule such as "not yourself" or "not the
 * last active admin" shows as a disabled button with the server's reason, before any request.
 * Blocking and a password reset end the user's sessions (backend tokens_valid_after).
 */
export function OfficeUsersPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseUsers(searchParams), [searchParams])
  const users = useAdminUsers(usersQuery(state))
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<StaffCreated | null>(null)
  useDocumentTitle(t('admin.users.title'))

  const go = (next: UsersState) => setSearchParams(usersSearch(next))

  const fields: FilterField[] = [
    { kind: 'text', name: 'q', label: t('admin.users.search'), placeholder: t('admin.users.searchPlaceholder'), maxLength: 100 },
    ...(state.tab === 'staff' ? [{
      kind: 'select' as const, name: 'role', label: t('admin.users.col.role'),
      options: STAFF_ROLES.map((role) => ({ value: role, label: roleLabel(t, role) })),
    }] : []),
    {
      kind: 'select', name: 'is_active', label: t('admin.users.status'),
      options: [{ value: 'true', label: t('admin.users.active') }, { value: 'false', label: t('admin.users.blocked') }],
    },
  ]

  const columns: TableColumnsType<AdminUser> = [
    {
      title: t('admin.users.col.name'), key: 'name', width: 220,
      render: (_, row) => (
        <Button type="link" className="admin-link-button" onClick={() => go({ ...state, user: row.id })}>
          {row.last_name} {row.first_name}
        </Button>
      ),
    },
    { title: t('admin.users.col.phone'), dataIndex: 'phone', width: 160 },
    { title: t('admin.users.col.email'), dataIndex: 'email', width: 230 },
    { title: t('admin.users.col.role'), key: 'role', width: 170, render: (_, row) => <Tag>{roleLabel(t, row.role)}</Tag> },
    { title: t('admin.users.col.status'), key: 'status', width: 150, render: (_, row) => <ActiveTag active={row.is_active} /> },
    {
      title: t('admin.users.col.registered'), dataIndex: 'created_at', width: 170,
      render: (value: string) => formatKyivDateTime(value),
    },
  ]

  if (users.error instanceof ApiError && users.error.status === 403) return <OfficeForbidden />

  return (
    <Flex vertical gap={16}>
      <Flex justify="space-between" align="center" wrap gap={12}>
        <h1 className="office-page-title">{t('admin.users.title')}</h1>
        {state.tab === 'staff' && (
          <Button type="primary" icon={<PlusOutlined aria-hidden />} onClick={() => setCreating(true)}>
            {t('admin.users.create.button')}
          </Button>
        )}
      </Flex>
      <Tabs activeKey={state.tab} aria-label={t('admin.users.tabs')}
        onChange={(key) => go({ tab: key as UsersState['tab'], page: 1 })}
        items={USER_TABS.map((tab) => ({ key: tab, label: t(`admin.users.tab.${tab}`) }))} />
      <FilterBar fields={fields} values={usersFilterValues(state)} onApply={(values) => go(usersFromFilters(state, values))} />
      {users.isError && !users.data ? (
        <ApiErrorState error={users.error} onRetry={() => void users.refetch()} title={t('admin.users.loadFailed')} />
      ) : (
        <Table<AdminUser> rowKey="id" columns={columns} dataSource={users.data?.items ?? []}
          loading={users.isFetching && !users.data} scroll={{ x: 1100 }}
          locale={{ emptyText: t('admin.users.empty') }}
          onChange={(pagination) => go({ ...state, page: pagination.current ?? 1 })}
          pagination={{
            current: state.page, pageSize: USERS_PAGE_SIZE, total: users.data?.total ?? 0, showSizeChanger: false,
            showTotal: (total, [from, to]) => t('admin.pagination', { from, to, total }),
          }} />
      )}
      <UserDrawer userId={state.user ?? null} onClose={() => go({ ...state, user: undefined })} />
      <CreateStaffModal open={creating} onClose={() => setCreating(false)} onCreated={setCreated} />
      <TemporaryPasswordModal created={created} onClose={() => setCreated(null)} />
    </Flex>
  )
}

function ActiveTag({ active }: { active: boolean }) {
  const { t } = useTranslation()
  return active ? <Tag color="success">{t('admin.users.active')}</Tag> : <Tag color="error">{t('admin.users.blocked')}</Tag>
}

const find = (user: AdminUser, action: UserAdminAction): UserActionInfo | undefined =>
  user.user_actions.find((a) => a.action === action)

/** The user's card with the actions the server allows. */
function UserDrawer({ userId, onClose }: { userId: number | null; onClose: () => void }) {
  const { t } = useTranslation()
  const user = useAdminUser(userId)
  const action = useAdminAction(useMemo(() => [adminKeys.users, adminKeys.user(userId ?? 0)], [userId]))
  const [dialog, setDialog] = useState<Dialog>(null)
  const data = user.data

  const button = (name: UserAdminAction, label: string, open: Dialog, danger = false) => {
    const info = data && find(data, name)
    if (!info) return null
    return (
      <ServerActionButton key={name} info={info} busy={action.busy !== null} danger={danger}
        onClick={() => { action.clearError(); setDialog(open) }}>
        {label}
      </ServerActionButton>
    )
  }
  const closeDialog = () => setDialog(null)
  const errorText = action.error && !action.error.issues.length ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  return (
    <Drawer open={userId !== null} onClose={onClose} size={560} destroyOnHidden
      title={data ? `${data.last_name} ${data.first_name}` : t('admin.users.card')}>
      {user.isError ? (
        <ApiErrorState error={user.error} onRetry={() => void user.refetch()} title={t('admin.users.cardFailed')} />
      ) : !data ? (
        <Spin aria-label={t('admin.loading')} />
      ) : (
        <Flex vertical gap={16}>
          <Descriptions column={1} bordered size="small" items={[
            { key: 'phone', label: t('admin.users.col.phone'), children: data.phone },
            { key: 'email', label: t('admin.users.col.email'), children: data.email },
            { key: 'role', label: t('admin.users.col.role'), children: roleLabel(t, data.role) },
            { key: 'status', label: t('admin.users.col.status'), children: <ActiveTag active={data.is_active} /> },
            { key: 'created', label: t('admin.users.col.registered'), children: formatKyivDateTime(data.created_at) },
            { key: 'updated', label: t('admin.users.updated'), children: formatKyivDateTime(data.updated_at) },
          ]} />
          <Space wrap>
            {button('edit', t('admin.users.edit.button'), 'edit')}
            {button('change_role', t('admin.users.role.button'), 'role')}
            {button('block', t('admin.users.block.button'), 'block', true)}
            {button('unblock', t('admin.users.unblock.button'), 'unblock')}
            {button('reset_password', t('admin.users.reset.button'), 'reset')}
          </Space>
          {errorText && dialog === null && (
            <Alert type="error" showIcon role="alert" closable={{ onClose: action.clearError }} title={errorText} />
          )}
          <EditUserModal open={dialog === 'edit'} user={data} action={action} error={errorText} onClose={closeDialog} />
          <ChangeRoleModal open={dialog === 'role'} user={data} action={action} error={errorText} onClose={closeDialog} />
          <BlockModal open={dialog === 'block' || dialog === 'unblock'} block={dialog === 'block'} user={data}
            action={action} error={errorText} onClose={closeDialog} />
          <ResetPasswordModal open={dialog === 'reset'} user={data} action={action} error={errorText} onClose={closeDialog} />
        </Flex>
      )}
    </Drawer>
  )
}

type Action = ReturnType<typeof useAdminAction>
interface DialogProps {
  open: boolean
  user: AdminUser
  action: Action
  error: string | null
  onClose: () => void
}

function phoneRules(t: TFunction): Rule[] {
  return [
    { required: true, whitespace: true, message: t('auth.phoneRequired') },
    { validator: (_: unknown, value?: string) => !value?.trim() || isValidPhone(value)
      ? Promise.resolve() : Promise.reject(new Error(t('auth.phoneFormat'))) },
  ]
}

interface ContactValues { last_name: string; first_name: string; phone: string; email: string }
const CONTACT_FIELDS = ['last_name', 'first_name', 'phone', 'email'] as const

/** Staff have no citizenship: names in Ukrainian letters, as the backend checks for them. */
function ContactFields({ initial }: { initial?: ContactValues }) {
  const { t } = useTranslation()
  return (
    <>
      <Form.Item name="last_name" label={t('auth.lastName')} initialValue={initial?.last_name}
        rules={nameRules(t, 'auth.lastNameRequired', undefined)}>
        <Input autoComplete="off" />
      </Form.Item>
      <Form.Item name="first_name" label={t('auth.firstName')} initialValue={initial?.first_name}
        rules={nameRules(t, 'auth.firstNameRequired', undefined)}>
        <Input autoComplete="off" />
      </Form.Item>
      <Form.Item name="phone" label={t('auth.phone')} initialValue={initial?.phone} rules={phoneRules(t)}>
        <Input type="tel" inputMode="tel" autoComplete="off" placeholder="+380XXXXXXXXX" />
      </Form.Item>
      <Form.Item name="email" label={t('auth.email')} initialValue={initial?.email} rules={emailRules(t)}>
        <Input type="email" autoComplete="off" />
      </Form.Item>
    </>
  )
}

const contactsOf = (values: ContactValues) => ({
  last_name: values.last_name.trim(), first_name: values.first_name.trim(),
  phone: normalizePhone(values.phone), email: values.email.trim(),
})

function EditUserModal({ open, user, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const [form] = Form.useForm<ContactValues>()
  useFieldIssues(form, open ? action.error : null, CONTACT_FIELDS)
  const submit = async (values: ContactValues) =>
    (await action.run('edit', () => adminUsersApi.update(user.id, contactsOf(values)))) !== null
  return (
    <FormModal open={open} title={t('admin.users.edit.title')} okText={t('admin.save')} cancelText={t('admin.cancel')}
      busy={action.busy === 'edit'} error={error} form={form} onCancel={onClose} onSubmit={submit}>
      <ContactFields initial={{ last_name: user.last_name, first_name: user.first_name, phone: user.phone, email: user.email }} />
    </FormModal>
  )
}

function ChangeRoleModal({ open, user, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  // Field names differ from the filter bar's `role`: ids must be unique on the page (label → field).
  const [form] = Form.useForm<{ new_role: UserRole }>()
  const submit = async ({ new_role }: { new_role: UserRole }) =>
    (await action.run('role', () => adminUsersApi.update(user.id, { role: new_role }))) !== null
  return (
    <FormModal open={open} title={t('admin.users.role.title')} okText={t('admin.users.role.ok')} cancelText={t('admin.cancel')}
      busy={action.busy === 'role'} error={error} form={form} onCancel={onClose} onSubmit={submit}
      warning={t('admin.users.role.warning')}>
      <Form.Item name="new_role" label={t('admin.users.role.label')} rules={[{ required: true, message: t('admin.users.role.required') }]}>
        <Select options={STAFF_ROLES.filter((role) => role !== user.role).map((role) => ({ value: role, label: roleLabel(t, role) }))} />
      </Form.Item>
      <Typography.Paragraph type="secondary">
        {t('admin.users.role.current', { role: roleLabel(t, user.role) })}
      </Typography.Paragraph>
    </FormModal>
  )
}

function BlockModal({ open, block, user, action, error, onClose }: DialogProps & { block: boolean }) {
  const { t } = useTranslation()
  const [form] = Form.useForm<object>()
  const name = block ? 'block' : 'unblock'
  const who = `${user.last_name} ${user.first_name}`
  const title = block ? t('admin.users.block.title', { name: who }) : t('admin.users.unblock.title', { name: who })
  const submit = async () => (await action.run(name, () => adminUsersApi.update(user.id, { is_active: !block }))) !== null
  return (
    <FormModal open={open} danger={block} form={form} busy={action.busy === name} error={error}
      title={title}
      okText={t(block ? 'admin.users.block.ok' : 'admin.users.unblock.ok')} cancelText={t('admin.cancel')}
      warning={t(block ? 'admin.users.block.warning' : 'admin.users.unblock.warning')} onCancel={onClose} onSubmit={submit} />
  )
}

interface ResetValues { new_password: string; new_password_repeat: string }
const RESET_FIELDS = ['new_password'] as const

function ResetPasswordModal({ open, user, action, error, onClose }: DialogProps) {
  const { t } = useTranslation()
  const [form] = Form.useForm<ResetValues>()
  const value = Form.useWatch('new_password', form) ?? ''
  useFieldIssues(form, open ? action.error : null, RESET_FIELDS)
  const submit = async (values: ResetValues) =>
    (await action.run('reset', () => adminUsersApi.resetPassword(user.id, values.new_password))) !== null
  return (
    <FormModal open={open} title={t('admin.users.reset.title', { name: `${user.last_name} ${user.first_name}` })}
      okText={t('admin.users.reset.ok')} cancelText={t('admin.cancel')} busy={action.busy === 'reset'} error={error}
      form={form} onCancel={onClose} onSubmit={submit} warning={t('admin.users.reset.warning')}>
      <Form.Item name="new_password" label={t('admin.users.reset.password')} extra={<PasswordRules value={value} />}
        rules={newPasswordRules(t)}>
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item name="new_password_repeat" label={t('auth.passwordRepeat')} dependencies={['new_password']}
        rules={repeatRules(t, 'new_password')}>
        <Input.Password autoComplete="new-password" />
      </Form.Item>
    </FormModal>
  )
}

interface CreateValues extends ContactValues { staff_role: UserRole }
const CREATE_FIELDS = [...CONTACT_FIELDS, 'staff_role'] as const

/** «Додати співробітника»: the server generates the temporary password (no password field here). */
function CreateStaffModal({ open, onClose, onCreated }: {
  open: boolean; onClose: () => void; onCreated: (created: StaffCreated) => void
}) {
  const { t } = useTranslation()
  const [form] = Form.useForm<CreateValues>()
  const action = useAdminAction(KEYS)
  useFieldIssues(form, action.error, CREATE_FIELDS)
  const errorText = action.error && !action.error.issues.length ? actionErrorText(action.error, t('office.forbiddenTitle')) : null
  const submit = async (values: CreateValues) => {
    const created = await action.run('create', () => adminUsersApi.create({ role: values.staff_role, ...contactsOf(values) }))
    if (!created) return false
    onCreated(created)
    return true
  }
  return (
    <FormModal open={open} title={t('admin.users.create.title')} okText={t('admin.users.create.ok')} cancelText={t('admin.cancel')}
      busy={action.busy === 'create'} error={errorText} form={form}
      onCancel={() => { action.clearError(); onClose() }} onSubmit={submit} warning={t('admin.users.create.note')}>
      <Form.Item name="staff_role" label={t('admin.users.role.label')} rules={[{ required: true, message: t('admin.users.role.required') }]}>
        <Select options={STAFF_ROLES.map((role) => ({ value: role, label: roleLabel(t, role) }))} />
      </Form.Item>
      <ContactFields />
    </FormModal>
  )
}

/** The temporary password, shown once: it is not stored anywhere and cannot be shown again. */
function TemporaryPasswordModal({ created, onClose }: { created: StaffCreated | null; onClose: () => void }) {
  const { t } = useTranslation()
  const password = created?.temporary_password
  return (
    <Modal open={created !== null} title={t('admin.users.temp.title')} onCancel={onClose} onOk={onClose}
      okText={t('admin.users.temp.ok')} mask={{ closable: false }} destroyOnHidden
      footer={(_, { OkBtn }) => <OkBtn />}>
      {created && (
        <Flex vertical gap={12}>
          <Typography.Paragraph>
            {t('admin.users.temp.created', { name: `${created.last_name} ${created.first_name}`, role: roleLabel(t, created.role) })}
          </Typography.Paragraph>
          {password && (
            <>
              <div>
                <Typography.Text type="secondary">{t('admin.users.temp.label')}</Typography.Text>
                <div className="admin-temp-password">
                  <Typography.Text code copyable={{ text: password, tooltips: [t('admin.users.temp.copy'), t('admin.users.temp.copied')] }}
                    data-testid="temporary-password">
                    {password}
                  </Typography.Text>
                </div>
              </div>
              <Alert type="warning" showIcon role="note" title={t('admin.users.temp.note')} />
              <Typography.Text type="secondary">{t('admin.users.temp.once')}</Typography.Text>
            </>
          )}
        </Flex>
      )}
    </Modal>
  )
}
