import { Alert, Button, Checkbox, DatePicker, Form, Input, Select, Typography } from 'antd'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useEffect, useMemo, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'
import { registerRequest } from '../../api/auth'
import { useCountries } from '../../api/reference'
import { HelpGuide } from '../../components/HelpGuide'
import { mapFormError } from '../../features/auth/authErrors'
import { birthDateRules, emailRules, nameRules, newPasswordRules, repeatRules } from '../../features/auth/formRules'
import { PasswordRules } from '../../features/auth/PasswordRules'
import { homeFor, safeRedirect } from '../../features/auth/redirect'
import { isValidPhone, normalizePhone } from '../../features/auth/rules'
import { useAuth } from '../../features/auth/useAuth'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { kyivToday } from '../../utils/format'
import { AuthCard } from './AuthCard'

interface RegisterValues {
  phone: string
  email: string
  password: string
  password_repeat: string
  last_name: string
  first_name: string
  birth_date: Dayjs | null
  citizenship_id: number | null
  consent: boolean
}

/** Form fields the backend validates (422 loc) — the rest go to the Alert. */
const FIELDS = ['phone', 'email', 'password', 'last_name', 'first_name', 'birth_date', 'citizenship_id', 'consent'] as const

/** /register (spec 03 §2, ТЗ 4.5.1, form 4.6.1.1): the fields POST /auth/register accepts. */
export function RegisterPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('auth.registerTitle'))
  const { user, status, login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const redirect = safeRedirect(params.get('redirect'))
  const countries = useCountries()
  const ukraine = useMemo(() => countries.data?.find((c) => c.iso_code === 'UA'), [countries.data])
  const [form] = Form.useForm<RegisterValues>()
  const password = Form.useWatch('password', form) ?? ''
  const citizenship = Form.useWatch('citizenship_id', form)
  const isUkrainian = citizenship === undefined || citizenship === null || citizenship === ukraine?.id
  const [submitted, setSubmitted] = useState(false)
  const [alert, setAlert] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  // Most clients are citizens of Ukraine: preselect it once the list has loaded.
  useEffect(() => {
    if (ukraine && form.getFieldValue('citizenship_id') == null) form.setFieldValue('citizenship_id', ukraine.id)
  }, [ukraine, form])

  if (status === 'user' && user && !sending) return <Navigate to={redirect ?? homeFor(user.role)} replace />

  const submit = async (values: RegisterValues) => {
    setAlert(null)
    setSending(true)
    const phone = normalizePhone(values.phone)
    try {
      await registerRequest({
        phone, email: values.email.trim(), password: values.password,
        last_name: values.last_name.trim(), first_name: values.first_name.trim(),
        birth_date: values.birth_date!.format('YYYY-MM-DD'), citizenship_id: values.citizenship_id!,
        consent: values.consent,
      })
    } catch (err) {
      const mapped = mapFormError(err, FIELDS)
      // Field names come from FIELDS, so they are names of this form.
      form.setFields(mapped.fields as Parameters<typeof form.setFields>[0])
      setAlert(mapped.alert)
      setSending(false)
      const first = mapped.fields[0]?.name as keyof RegisterValues | undefined
      if (first) form.scrollToField(first, { focus: true, block: 'center' })
      return
    }
    // The backend returns no token on registration: sign in with the same data right away.
    try {
      const signedIn = await login(phone, values.password)
      navigate(redirect ?? homeFor(signedIn.role), { replace: true })
    } catch {
      navigate(redirect ? `/login?${new URLSearchParams({ redirect })}` : '/login',
        { replace: true, state: { accountCreated: true } })
    }
  }

  const loginLink = redirect ? `/login?${new URLSearchParams({ redirect })}` : '/login'
  const nameRule = (requiredKey: 'auth.lastNameRequired' | 'auth.firstNameRequired') =>
    nameRules(t, requiredKey, ukraine?.id)
  const nameHint = t(isUkrainian ? 'auth.nameHintUa' : 'auth.nameHintLatin')

  return (
    <AuthCard title={t('auth.registerTitle')}>
      <Form form={form} layout="vertical" requiredMark onFinish={submit} noValidate
        onFinishFailed={() => setSubmitted(true)}
        validateTrigger={submitted ? ['onChange', 'onBlur'] : 'onBlur'}
        scrollToFirstError={{ focus: true, block: 'center' }}
        initialValues={{ consent: false }}>
        <Form.Item name="phone" label={t('auth.phone')} extra={t('auth.phoneHint')}
          rules={[{ required: true, whitespace: true, message: t('auth.phoneRequired') },
            { validator: (_, value?: string) => !value?.trim() || isValidPhone(value)
              ? Promise.resolve() : Promise.reject(new Error(t('auth.phoneFormat'))) }]}>
          <Input type="tel" autoComplete="tel" inputMode="tel" placeholder="+380XXXXXXXXX" />
        </Form.Item>
        <Form.Item name="email" label={t('auth.email')} extra={t('auth.emailHint')}
          rules={emailRules(t)}>
          <Input type="email" autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label={t('auth.password')}
          extra={<PasswordRules value={password} />}
          rules={newPasswordRules(t)}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item name="password_repeat" label={t('auth.passwordRepeat')} dependencies={['password']}
          rules={repeatRules(t, 'password')}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>

        <Form.Item name="citizenship_id" label={t('auth.citizenship')}
          rules={[{ required: true, message: t('auth.citizenshipRequired') }]}>
          <Select showSearch={{ optionFilterProp: 'label' }} loading={countries.isLoading}
            options={countries.data?.map((c) => ({ value: c.id, label: c.name_uk }))} />
        </Form.Item>
        {/* dependencies: a new citizenship re-checks names already typed. */}
        <Form.Item name="last_name" label={t('auth.lastName')} extra={nameHint} dependencies={['citizenship_id']}
          rules={nameRule('auth.lastNameRequired')}>
          <Input autoComplete="family-name" />
        </Form.Item>
        <Form.Item name="first_name" label={t('auth.firstName')} extra={nameHint} dependencies={['citizenship_id']}
          rules={nameRule('auth.firstNameRequired')}>
          <Input autoComplete="given-name" />
        </Form.Item>
        <Form.Item name="birth_date" label={t('auth.birthDate')} extra={t('auth.birthDateHint')}
          rules={birthDateRules(t)}>
          <DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} placeholder="ДД.ММ.РРРР"
            defaultPickerValue={dayjs(kyivToday()).subtract(25, 'year')}
            disabledDate={(day) => day.isAfter(dayjs(kyivToday()), 'day')} />
        </Form.Item>

        <Form.Item name="consent" valuePropName="checked"
          rules={[{ validator: (_, value?: boolean) => value
            ? Promise.resolve() : Promise.reject(new Error(t('auth.consentRequired'))) }]}>
          <Checkbox>
            <Trans i18nKey="auth.consent" components={{
              terms: <Link to="/terms" target="_blank" />, privacy: <Link to="/privacy" target="_blank" />,
            }} />
          </Checkbox>
        </Form.Item>

        {alert && <Alert type="error" showIcon role="alert" className="auth-alert" title={alert} />}
        <Button type="primary" htmlType="submit" block loading={sending} onClick={() => setSubmitted(true)}>
          {t('auth.submitRegister')}
        </Button>
      </Form>

      <div className="auth-footer">
        <Typography.Text>{t('auth.haveAccount')}</Typography.Text>{' '}
        <Link to={loginLink}>{t('auth.toLogin')}</Link>
      </div>

      <HelpGuide content={{
        title: t('help.registerTitle'),
        steps: (['1', '2', '3', '4', '5', '6'] as const).map((n) => t(`help.registerSteps.${n}`)),
        link: { to: loginLink, label: t('help.toLogin') },
      }} />
    </AuthCard>
  )
}
