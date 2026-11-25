import { PlusOutlined } from '@ant-design/icons'
import {
  Alert, App, Button, Card, Descriptions, Flex, Form, Input, InputNumber, Modal, Space, Spin, Switch, Table, Tag, Typography,
} from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { adminKeys, languagesApi, saveSettings, useAdminSettings, useGatewayStatus, useLanguages } from '../../../api/admin'
import { ApiError } from '../../../api/client'
import type { AdminSettings, Language, ReferenceAction, SettingsIn } from '../../../api/types'
import { ApiErrorState } from '../../../components/ApiErrorState'
import { FormModal } from '../../../components/office/FormModal'
import { ServerActionButton } from '../../../components/office/ServerActionButton'
import { useAdminAction } from '../../../features/admin/useAdminAction'
import { isValidEmail, isValidPhone, normalizePhone } from '../../../features/auth/rules'
import { actionErrorText } from '../../../features/office/useOfficeAction'
import { useDocumentTitle } from '../../../hooks/useDocumentTitle'
import { useUnsavedChanges } from '../../../hooks/useUnsavedChanges'
import { formatKyivDateTime } from '../../../utils/format'
import { OfficeForbidden } from '../OfficeHome'
import { useFieldIssues } from './formErrors'
import '../../../layouts/OfficeLayout.css'
import './admin.css'

type Key = keyof SettingsIn
type Values = Partial<Record<Key, string | number | boolean | null>>

/** The groups of form 4.6.4.1 (spec 13 §3); each saves only its own fields. */
const GROUPS = {
  booking: ['eur_rate', 'usd_rate', 'acquiring_percent', 'booking_timeout_min', 'bank_transfer_hold_hours'],
  reviews: ['review_premoderation'],
  contacts: ['support_phone', 'support_email', 'support_address', 'system_email'],
} as const satisfies Record<string, readonly Key[]>
type Group = keyof typeof GROUPS
const NUMBER_KEYS = new Set<Key>(['eur_rate', 'usd_rate', 'acquiring_percent', 'booking_timeout_min', 'bank_transfer_hold_hours'])
/** Decimal values travel as strings (money and rates are never floats, CLAUDE.md). */
const DECIMAL_KEYS = new Set<Key>(['eur_rate', 'usd_rate', 'acquiring_percent'])

const valueOf = (settings: AdminSettings, key: Key) => settings[key as keyof AdminSettings] as string | number | boolean
const same = (a: unknown, b: unknown) => (typeof a === 'string' && typeof b === 'string' && a !== '' && b !== '' && !Number.isNaN(Number(a)) && !Number.isNaN(Number(b)))
  ? Number(a) === Number(b) : a === b

/**
 * «Налаштування» (spec 13 §3, form 4.6.4.1): only the settings the API has, in groups with their
 * own «Зберегти» (a partial PUT of that group), a short description and the limits from the
 * server's `rules` next to each field, and who changed it last. Maintenance mode has its own card:
 * turning it on asks first, and while it is on OfficeLayout shows an Alert on every page.
 * Payment keys stay in backend/.env: the gateway card only says what is configured.
 */
export function OfficeSettingsPage() {
  const { t } = useTranslation()
  const settings = useAdminSettings()
  const [dirty, setDirty] = useState<Record<string, boolean>>({})
  useUnsavedChanges(Object.values(dirty).some(Boolean))
  useDocumentTitle(t('admin.settings.title'))

  const markDirty = useMemo(() => (group: string, value: boolean) =>
    setDirty((current) => (current[group] === value ? current : { ...current, [group]: value })), [])

  if (settings.error instanceof ApiError && settings.error.status === 403) return <OfficeForbidden />
  if (settings.isError && !settings.data) {
    return <ApiErrorState error={settings.error} onRetry={() => void settings.refetch()} title={t('admin.settings.loadFailed')} />
  }
  if (!settings.data) return <Spin aria-label={t('admin.loading')} />
  const data = settings.data

  return (
    <Flex vertical gap={16}>
      <h1 className="office-page-title">{t('admin.settings.title')}</h1>
      <MaintenanceCard settings={data} />
      <SettingsGroup group="booking" settings={data} onDirty={markDirty} />
      <SettingsGroup group="reviews" settings={data} onDirty={markDirty}
        extra={(
          <Descriptions size="small" column={1} items={[
            { key: 'photos', label: t('admin.settings.limits.photos'), children: data.limits.max_review_photos },
            { key: 'mb', label: t('admin.settings.limits.photoMb'), children: t('admin.settings.limits.mb', { value: data.limits.max_review_photo_mb }) },
          ]} />
        )} />
      <SettingsGroup group="contacts" settings={data} onDirty={markDirty} />
      <LanguagesCard />
      <GatewayCard />
    </Flex>
  )
}

function changedNote(t: TFunction, settings: AdminSettings, key: Key): ReactNode {
  const change = settings.changes[key]
  if (!change) return null
  const when = formatKyivDateTime(change.updated_at)
  const text: string = change.updated_by_name
    ? t('admin.settings.changedBy', { when, who: change.updated_by_name })
    : t('admin.settings.changed', { when })
  return <Typography.Text type="secondary" className="admin-changed">{text}</Typography.Text>
}

function SettingsGroup({ group, settings, onDirty, extra }: {
  group: Group; settings: AdminSettings; onDirty: (group: string, dirty: boolean) => void; extra?: ReactNode
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<Values>()
  const keys: readonly Key[] = GROUPS[group]
  const action = useAdminAction(useMemo(() => [adminKeys.settings], []))
  useFieldIssues(form, action.error, keys)
  // Only this group's server values: another group's save must not reset unsaved edits here.
  const initialKey = JSON.stringify(keys.map((key) => valueOf(settings, key)))
  const initial = useMemo(() => Object.fromEntries(keys.map((key, i) => [key, (JSON.parse(initialKey) as Values[Key][])[i]])) as Values,
    [keys, initialKey])
  const values = Form.useWatch([], form) as Values | undefined
  const changes = useMemo(() => {
    const out: SettingsIn = {}
    for (const key of keys) {
      const value = values?.[key]
      if (value === undefined || same(value, initial[key])) continue
      ;(out as Record<string, unknown>)[key] = typeof value === 'string' ? value.trim() : value
    }
    return out
  }, [values, initial, keys])
  const dirty = Object.keys(changes).length > 0
  const [saved, setSaved] = useState(false)

  useEffect(() => { onDirty(group, dirty) }, [dirty, group, onDirty])
  useEffect(() => { form.setFieldsValue(initial) }, [form, initial])

  const save = async () => {
    try {
      await form.validateFields()
    } catch {
      return
    }
    const body = { ...changes }
    if (typeof body.support_phone === 'string' && body.support_phone) body.support_phone = normalizePhone(body.support_phone)
    setSaved(false)
    const result = await action.run(`save-${group}`, () => saveSettings(body))
    if (result) {
      queryClient.setQueryData(adminKeys.settings, result)
      setSaved(true)
    }
  }
  const errorText = action.error && !action.error.issues.length ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  return (
    <Card className="admin-settings-card" title={<h2 className="admin-card-title">{t(`admin.settings.group.${group}`)}</h2>}>
      <Form form={form} layout="vertical" initialValues={initial} validateTrigger={['onBlur', 'onChange']}
        onValuesChange={() => setSaved(false)}>
        {keys.map((key) => <SettingField key={key} name={key} settings={settings} />)}
      </Form>
      {extra}
      {errorText && <Alert type="error" showIcon role="alert" title={errorText} className="admin-alert" />}
      {saved && <Alert type="success" showIcon role="status" title={t('admin.settings.saved')} className="admin-alert" />}
      <Space>
        <Button type="primary" onClick={() => void save()} loading={action.busy === `save-${group}`} disabled={!dirty}>
          {t('admin.settings.save', { group: t(`admin.settings.group.${group}`) })}
        </Button>
        {dirty && (
          <Button onClick={() => form.setFieldsValue(initial)} disabled={action.busy !== null}>{t('admin.settings.reset')}</Button>
        )}
      </Space>
    </Card>
  )
}

function SettingField({ name, settings }: { name: Key; settings: AdminSettings }) {
  const { t } = useTranslation()
  const rule = settings.rules[name]
  const label: string = t(`admin.settings.field.${name}.label`)
  const help: string = t(`admin.settings.field.${name}.help`)
  const extra = (
    <Space orientation="vertical" size={0}>
      <span>{help}</span>
      {rule?.min != null && rule.max != null && (
        <span>{t('admin.settings.range', { min: rule.min, max: rule.max })}</span>
      )}
      {changedNote(t, settings, name)}
    </Space>
  )
  if (name === 'review_premoderation') {
    return (
      <Form.Item name={name} label={label} extra={extra} valuePropName="checked">
        <Switch />
      </Form.Item>
    )
  }
  if (NUMBER_KEYS.has(name)) {
    const places = rule?.places ?? 0
    return (
      <Form.Item name={name} label={label} extra={extra}
        rules={[{ required: true, message: t('admin.settings.required') }]}>
        {DECIMAL_KEYS.has(name) ? (
          <InputNumber<string> stringMode min={rule?.min ?? undefined} max={rule?.max ?? undefined} precision={places}
            step={places >= 4 ? '0.0001' : '0.01'} className="admin-setting-number" />
        ) : (
          <InputNumber min={Number(rule?.min ?? 0)} max={Number(rule?.max ?? 1e6)} precision={0} className="admin-setting-number" />
        )}
      </Form.Item>
    )
  }
  const max = rule?.max_length ?? 255
  const rules = [{ max, message: t('admin.settings.tooLong', { max }) }] as Array<Record<string, unknown>>
  if (name === 'system_email') rules.unshift({ required: true, whitespace: true, message: t('admin.settings.required') })
  if (name === 'system_email' || name === 'support_email') {
    rules.push({ validator: (_: unknown, value?: string) => !value?.trim() || isValidEmail(value)
      ? Promise.resolve() : Promise.reject(new Error(t('auth.emailFormat'))) })
  }
  if (name === 'support_phone') {
    rules.push({ validator: (_: unknown, value?: string) => !value?.trim() || isValidPhone(value)
      ? Promise.resolve() : Promise.reject(new Error(t('auth.phoneFormat'))) })
  }
  return (
    <Form.Item name={name} label={label} extra={extra} rules={rules}>
      {name === 'support_address'
        ? <Input.TextArea rows={2} maxLength={max} showCount />
        : <Input type={name.endsWith('email') ? 'email' : name === 'support_phone' ? 'tel' : 'text'} />}
    </Form.Item>
  )
}

/** Maintenance mode (form 4.6.4.1, field 7): on only after a warning, off at once. */
function MaintenanceCard({ settings }: { settings: AdminSettings }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const action = useAdminAction(useMemo(() => [adminKeys.settings], []))
  const [asking, setAsking] = useState(false)
  // null = not edited: the field shows the saved message.
  const [draft, setDraft] = useState<string | null>(null)
  const message = draft ?? settings.maintenance_message
  const max = settings.rules.maintenance_message?.max_length ?? 500
  const on = settings.maintenance_mode

  const save = async (body: SettingsIn) => {
    const result = await action.run('maintenance', () => saveSettings(body))
    if (result) {
      queryClient.setQueryData(adminKeys.settings, result)
      if ('maintenance_message' in body) setDraft(null)
    }
    return result !== null
  }
  const messageChanged = message.trim() !== settings.maintenance_message
  const errorText = action.error ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  return (
    <Card id="maintenance" className="admin-settings-card"
      title={<h2 className="admin-card-title">{t('admin.settings.group.maintenance')}</h2>}
      extra={on ? <Tag color="warning">{t('admin.settings.maintenance.on')}</Tag> : <Tag>{t('admin.settings.maintenance.off')}</Tag>}>
      <Flex vertical gap={12}>
        <Typography.Paragraph className="admin-intro">{t('admin.settings.maintenance.help')}</Typography.Paragraph>
        <label className="admin-switch-label">
          <Switch checked={on} loading={action.busy === 'maintenance'} aria-describedby="maintenance-help"
            onChange={(next) => { action.clearError(); if (next) setAsking(true); else void save({ maintenance_mode: false }) }} />
          <span>{t('admin.settings.maintenance.switch')}</span>
        </label>
        <span id="maintenance-help" className="visually-hidden">{t('admin.settings.maintenance.help')}</span>
        <Form layout="vertical">
          <Form.Item label={t('admin.settings.field.maintenance_message.label')} htmlFor="maintenance-message"
            extra={<Space orientation="vertical" size={0}>
              <span>{t('admin.settings.field.maintenance_message.help')}</span>
              {changedNote(t, settings, 'maintenance_message')}
            </Space>}>
            <Input.TextArea id="maintenance-message" rows={2} maxLength={max} showCount value={message}
              placeholder={t('admin.settings.maintenance.defaultText')} onChange={(e) => setDraft(e.target.value)} />
          </Form.Item>
        </Form>
        {messageChanged && (
          <Button className="admin-align-start" onClick={() => void save({ maintenance_message: message.trim() })}
            loading={action.busy === 'maintenance'}>
            {t('admin.settings.maintenance.saveMessage')}
          </Button>
        )}
        {errorText && !asking && <Alert type="error" showIcon role="alert" title={errorText} />}
      </Flex>
      <Modal open={asking} title={t('admin.settings.maintenance.confirmTitle')} okText={t('admin.settings.maintenance.confirmOk')}
        cancelText={t('admin.cancel')} okButtonProps={{ danger: true, loading: action.busy === 'maintenance' }}
        onCancel={() => setAsking(false)} destroyOnHidden
        onOk={async () => {
          const body: SettingsIn = { maintenance_mode: true }
          if (messageChanged) body.maintenance_message = message.trim()
          if (await save(body)) setAsking(false)
        }}>
        <Alert type="warning" showIcon role="note" title={t('admin.settings.maintenance.confirmText')}
          description={t('admin.settings.maintenance.confirmStaff')} />
        {errorText && <Alert type="error" showIcon role="alert" title={errorText} className="admin-alert" />}
      </Modal>
    </Card>
  )
}

/** Site languages (form 4.6.4.1, field 5); the Ukrainian base language cannot be turned off. */
function LanguagesCard() {
  const { t } = useTranslation()
  const languages = useLanguages()
  const { modal } = App.useApp()
  const action = useAdminAction(useMemo(() => [adminKeys.languages], []))
  const [adding, setAdding] = useState(false)
  const [form] = Form.useForm<{ code: string; name: string }>()
  useFieldIssues(form, adding ? action.error : null, ['code', 'name'])
  const errorText = action.error && !action.error.issues.length ? actionErrorText(action.error, t('office.forbiddenTitle')) : null

  const info = (language: Language, name: ReferenceAction) => language.admin_actions.find((a) => a.action === name)
  const toggle = (language: Language) => {
    const name = language.is_enabled ? 'disable' : 'enable'
    const allowed = info(language, name)
    return allowed && (
      <ServerActionButton size="small" info={allowed} busy={action.busy !== null}
        onClick={() => void action.run(`${name}-${language.code}`, () => languagesApi.update(language.code, { is_enabled: !language.is_enabled }))}>
        {t(`admin.settings.languages.${name}`)}
      </ServerActionButton>
    )
  }
  const remove = (language: Language) => {
    const allowed = info(language, 'delete')
    return allowed && (
      <ServerActionButton size="small" danger info={allowed} busy={action.busy !== null}
        onClick={() => modal.confirm({
          title: t('admin.settings.languages.deleteTitle', { name: language.name }), okText: t('admin.references.delete.ok'),
          cancelText: t('admin.cancel'), okButtonProps: { danger: true },
          onOk: () => action.run(`delete-${language.code}`, () => languagesApi.remove(language.code)),
        })}>
        {t('admin.references.delete.button')}
      </ServerActionButton>
    )
  }

  return (
    <Card className="admin-settings-card" title={<h2 className="admin-card-title">{t('admin.settings.group.languages')}</h2>}
      extra={<Button icon={<PlusOutlined aria-hidden />} onClick={() => { action.clearError(); setAdding(true) }}>{t('admin.settings.languages.add')}</Button>}>
      <Typography.Paragraph type="secondary">{t('admin.settings.languages.help')}</Typography.Paragraph>
      {languages.isError ? (
        <ApiErrorState error={languages.error} onRetry={() => void languages.refetch()} title={t('admin.settings.languages.loadFailed')} />
      ) : (
        <Table<Language> rowKey="code" size="small" pagination={false} loading={languages.isPending} dataSource={languages.data ?? []}
          columns={[
            { title: t('admin.settings.languages.code'), dataIndex: 'code', width: 90 },
            { title: t('admin.settings.languages.name'), dataIndex: 'name' },
            { title: t('admin.users.col.status'), key: 'status', width: 140, render: (_, language) => language.is_enabled
              ? <Tag color="success">{t('admin.settings.languages.enabled')}</Tag> : <Tag>{t('admin.settings.languages.disabled')}</Tag> },
            { title: t('admin.references.col.actions'), key: 'actions', width: 260,
              render: (_, language) => <Space size={4} wrap>{toggle(language)}{remove(language)}</Space> },
          ]} />
      )}
      {errorText && !adding && <Alert type="error" showIcon role="alert" title={errorText} className="admin-alert" />}
      <FormModal open={adding} title={t('admin.settings.languages.addTitle')} okText={t('admin.references.create')} cancelText={t('admin.cancel')}
        busy={action.busy === 'add-language'} error={errorText} form={form} onCancel={() => { action.clearError(); setAdding(false) }}
        onSubmit={async (values) => (await action.run('add-language', () => languagesApi.create({
          code: values.code.trim().toLowerCase(), name: values.name.trim(), is_enabled: false }))) !== null}>
        <Form.Item name="code" label={t('admin.settings.languages.code')} extra={t('admin.settings.languages.codeHint')}
          rules={[{ required: true, message: t('admin.settings.required') }, { pattern: /^[A-Za-z]{2,5}$/, message: t('admin.settings.languages.codeFormat') }]}>
          <Input maxLength={5} className="admin-code-input" />
        </Form.Item>
        <Form.Item name="name" label={t('admin.settings.languages.name')}
          rules={[{ required: true, whitespace: true, message: t('admin.settings.required') }, { max: 50, message: t('admin.settings.tooLong', { max: 50 }) }]}>
          <Input />
        </Form.Item>
      </FormModal>
    </Card>
  )
}

/** Payment gateway status: what is configured, never the keys (they stay in backend/.env). */
function GatewayCard() {
  const { t } = useTranslation()
  const gateway = useGatewayStatus()
  const yesNo = (value: boolean) => (value ? t('admin.settings.gateway.yes') : t('admin.settings.gateway.no'))
  return (
    <Card className="admin-settings-card" title={<h2 className="admin-card-title">{t('admin.settings.group.gateway')}</h2>}>
      {gateway.isError ? (
        <ApiErrorState error={gateway.error} onRetry={() => void gateway.refetch()} title={t('admin.settings.gateway.loadFailed')} />
      ) : !gateway.data ? <Spin aria-label={t('admin.loading')} /> : (
        <Flex vertical gap={12}>
          <Descriptions size="small" column={1} bordered items={[
            { key: 'gateway', label: t('admin.settings.gateway.gateway'), children: gateway.data.gateway === 'stripe' ? 'Stripe' : t('admin.settings.gateway.mock') },
            { key: 'key', label: t('admin.settings.gateway.key'), children: gateway.data.stripe_key_configured
              ? t('admin.settings.gateway.keyMode', { mode: gateway.data.stripe_key_mode ?? '—' }) : yesNo(false) },
            { key: 'webhook', label: t('admin.settings.gateway.webhook'), children: yesNo(gateway.data.webhook_secret_configured) },
            { key: 'version', label: t('admin.settings.gateway.version'), children: gateway.data.stripe_api_version },
          ]} />
          <Typography.Text type="secondary">{gateway.data.how_to_change}</Typography.Text>
        </Flex>
      )}
    </Card>
  )
}
