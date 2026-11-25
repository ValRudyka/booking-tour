import { App, Alert, Button, Card, DatePicker, Descriptions, Form, Input, Select, Space, Typography } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { changePassword, updateProfile } from '../../api/profile'
import { useCountries } from '../../api/reference'
import type { User } from '../../api/types'
import { mapFormError } from '../../features/auth/authErrors'
import {
  birthDateRules, emailRules, nameRules, newPasswordRules, repeatRules,
} from '../../features/auth/formRules'
import { PasswordRules } from '../../features/auth/PasswordRules'
import { useAuth } from '../../features/auth/useAuth'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { useUnsavedChanges } from '../../hooks/useUnsavedChanges'
import { formatDate, kyivToday } from '../../utils/format'
import './CabinetPages.css'

const ISO = 'YYYY-MM-DD'

interface ProfileValues {
  email: string
  last_name: string
  first_name: string
  birth_date: Dayjs | null
  citizenship_id: number | null
}

/** Fields PATCH /auth/me accepts; the phone is the login and changes only through support. */
const PROFILE_FIELDS = ['email', 'last_name', 'first_name', 'birth_date', 'citizenship_id'] as const

function toValues(user: User): ProfileValues {
  return {
    email: user.email, last_name: user.last_name, first_name: user.first_name,
    birth_date: user.birth_date ? dayjs(user.birth_date, ISO) : null, citizenship_id: user.citizenship_id,
  }
}

/** /cabinet/profile (spec 08 §2, ТЗ 4.5.1.1, form 4.6.1.1): personal data and the password. */
export function ProfilePage() {
  const { t } = useTranslation()
  const title = t('cabinet.profile.title')
  useDocumentTitle(title)
  const { user } = useAuth()
  if (!user) return null    // RequireAuth renders the page only for a signed-in client
  return (
    <section aria-labelledby="profile-title">
      <h1 id="profile-title" className="cabinet-title">{title}</h1>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <PersonalData user={user} />
        <PasswordCard />
      </Space>
    </section>
  )
}

function PersonalData({ user }: { user: User }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { setUser } = useAuth()
  const countries = useCountries()
  const ukraine = useMemo(() => countries.data?.find((c) => c.iso_code === 'UA'), [countries.data])
  const [editing, setEditing] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [alert, setAlert] = useState<string | null>(null)
  const [form] = Form.useForm<ProfileValues>()
  const citizenship = Form.useWatch('citizenship_id', form)
  useUnsavedChanges(editing && dirty)

  const country = countries.data?.find((c) => c.id === user.citizenship_id)
  const isUkrainian = citizenship == null || citizenship === ukraine?.id
  const notSet = t('cabinet.profile.notSet')

  const startEditing = () => {
    form.setFieldsValue(toValues(user))
    setAlert(null)
    setDirty(false)
    setEditing(true)
  }
  const stopEditing = () => {
    setEditing(false)
    setDirty(false)
    setAlert(null)
  }

  const save = async (values: ProfileValues) => {
    setAlert(null)
    setSaving(true)
    try {
      const saved = await updateProfile({
        email: values.email.trim(), last_name: values.last_name.trim(), first_name: values.first_name.trim(),
        birth_date: values.birth_date!.format(ISO), citizenship_id: values.citizenship_id!,
      })
      setUser(saved)
      stopEditing()
      void message.success(t('cabinet.profile.saved'))
    } catch (err) {
      const mapped = mapFormError(err, PROFILE_FIELDS)
      form.setFields(mapped.fields as Parameters<typeof form.setFields>[0])
      setAlert(mapped.alert)
      const first = mapped.fields[0]?.name as keyof ProfileValues | undefined
      if (first) form.scrollToField(first, { focus: true, block: 'center' })
    } finally {
      setSaving(false)
    }
  }

  const nameHint = t(isUkrainian ? 'auth.nameHintUa' : 'auth.nameHintLatin')

  return (
    <Card title={<h2 className="cabinet-section-title">{t('cabinet.profile.personal')}</h2>}
      extra={!editing && <Button onClick={startEditing}>{t('cabinet.profile.edit')}</Button>}>
      {!editing ? (
        <Descriptions column={1} size="small" items={[
          { key: 'phone', label: t('auth.phone'), children: user.phone },
          { key: 'email', label: t('auth.email'), children: user.email },
          { key: 'last_name', label: t('auth.lastName'), children: user.last_name },
          { key: 'first_name', label: t('auth.firstName'), children: user.first_name },
          { key: 'birth_date', label: t('auth.birthDate'),
            children: user.birth_date ? formatDate(user.birth_date) : notSet },
          { key: 'citizenship', label: t('auth.citizenship'),
            children: user.citizenship_id == null ? notSet : country?.name_uk ?? '…' },
        ]} />
      ) : (
        <Form form={form} layout="vertical" requiredMark noValidate onFinish={save}
          onValuesChange={() => setDirty(true)} scrollToFirstError={{ focus: true, block: 'center' }}
          className="profile-form">
          <Form.Item label={t('auth.phone')} htmlFor="profile-phone" extra={t('cabinet.profile.phoneReadOnly')}>
            <Input id="profile-phone" value={user.phone} readOnly aria-readonly />
          </Form.Item>
          <Form.Item name="email" label={t('auth.email')} extra={t('auth.emailHint')} rules={emailRules(t)}>
            <Input type="email" autoComplete="email" />
          </Form.Item>
          <Form.Item name="citizenship_id" label={t('auth.citizenship')}
            rules={[{ required: true, message: t('auth.citizenshipRequired') }]}>
            <Select showSearch={{ optionFilterProp: 'label' }} loading={countries.isLoading}
              options={countries.data?.map((c) => ({ value: c.id, label: c.name_uk }))} />
          </Form.Item>
          {/* dependencies: a new citizenship re-checks the names (the alphabet depends on it). */}
          <Form.Item name="last_name" label={t('auth.lastName')} extra={nameHint} dependencies={['citizenship_id']}
            rules={nameRules(t, 'auth.lastNameRequired', ukraine?.id)}>
            <Input autoComplete="family-name" />
          </Form.Item>
          <Form.Item name="first_name" label={t('auth.firstName')} extra={nameHint} dependencies={['citizenship_id']}
            rules={nameRules(t, 'auth.firstNameRequired', ukraine?.id)}>
            <Input autoComplete="given-name" />
          </Form.Item>
          <Form.Item name="birth_date" label={t('auth.birthDate')} extra={t('auth.birthDateHint')}
            rules={birthDateRules(t)}>
            <DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} placeholder="ДД.ММ.РРРР"
              disabledDate={(day) => day.isAfter(dayjs(kyivToday()), 'day')} />
          </Form.Item>
          {alert && <Alert type="error" showIcon role="alert" className="profile-alert" title={alert} />}
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={saving}>{t('cabinet.profile.save')}</Button>
            <Button onClick={stopEditing} disabled={saving}>{t('cabinet.profile.cancel')}</Button>
          </Space>
        </Form>
      )}
    </Card>
  )
}

interface PasswordValues {
  current_password: string
  new_password: string
  new_password_repeat: string
}

const PASSWORD_FIELDS = ['current_password', 'new_password'] as const

function PasswordCard() {
  const { t } = useTranslation()
  const { endSessionAfterPasswordChange } = useAuth()
  const [form] = Form.useForm<PasswordValues>()
  const value = Form.useWatch('new_password', form) ?? ''
  const [sending, setSending] = useState(false)
  const [alert, setAlert] = useState<string | null>(null)

  const submit = async (values: PasswordValues) => {
    setAlert(null)
    setSending(true)
    try {
      await changePassword({ current_password: values.current_password, new_password: values.new_password })
    } catch (err) {
      const mapped = mapFormError(err, PASSWORD_FIELDS)
      form.setFields(mapped.fields as Parameters<typeof form.setFields>[0])
      setAlert(mapped.alert)
      setSending(false)
      return
    }
    // Every session has ended on the server, this one too: sign in again (not a 401 later).
    endSessionAfterPasswordChange()
  }

  return (
    <Card title={<h2 className="cabinet-section-title">{t('cabinet.profile.password')}</h2>}>
      <Typography.Paragraph type="secondary">{t('cabinet.profile.passwordNote')}</Typography.Paragraph>
      <Form form={form} layout="vertical" requiredMark noValidate onFinish={submit} className="profile-form">
        <Form.Item name="current_password" label={t('cabinet.profile.currentPassword')}
          rules={[{ required: true, message: t('auth.passwordRequired') }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item name="new_password" label={t('cabinet.profile.newPassword')}
          extra={<PasswordRules value={value} />} rules={newPasswordRules(t)}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item name="new_password_repeat" label={t('auth.passwordRepeat')} dependencies={['new_password']}
          rules={repeatRules(t, 'new_password')}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        {alert && <Alert type="error" showIcon role="alert" className="profile-alert" title={alert} />}
        <Button type="primary" htmlType="submit" loading={sending}>{t('cabinet.profile.changePassword')}</Button>
      </Form>
    </Card>
  )
}
