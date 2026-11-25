import { Alert, Button, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useSiteContacts } from '../../api/site'
import { AppLink } from '../../components/AppLink'
import { HelpGuide } from '../../components/HelpGuide'
import type { LoginLocationState } from '../../features/auth/authContext'
import { loginErrorText } from '../../features/auth/authErrors'
import { homeFor, safeRedirect } from '../../features/auth/redirect'
import { useAuth } from '../../features/auth/useAuth'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { AuthCard } from './AuthCard'

interface LoginValues {
  username: string
  password: string
}

/** /login (spec 03 §2): phone or e-mail + password; back to `redirect` afterwards. */
export function LoginPage() {
  const { t } = useTranslation()
  useDocumentTitle(t('auth.loginTitle'))
  const { user, status, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [params] = useSearchParams()
  const redirect = safeRedirect(params.get('redirect'))
  const state = location.state as LoginLocationState | null
  const [form] = Form.useForm<LoginValues>()
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [forgotOpen, setForgotOpen] = useState(false)

  // Already signed in: nothing to do here.
  if (status === 'user' && user && !sending) {
    return <Navigate to={redirect ?? homeFor(user.role)} replace />
  }

  const submit = async (values: LoginValues) => {
    setError(null)
    setSending(true)
    try {
      const signedIn = await login(values.username.trim(), values.password)
      navigate(redirect ?? homeFor(signedIn.role), { replace: true })
    } catch (err) {
      setError(loginErrorText(err))
      setSending(false)
    }
  }

  const registerLink = redirect ? `/register?${new URLSearchParams({ redirect })}` : '/register'

  return (
    <AuthCard title={t('auth.loginTitle')}>
      {state?.sessionExpired && <Alert type="warning" showIcon className="auth-alert" title={t('auth.sessionExpired')} />}
      {state?.accountCreated && <Alert type="success" showIcon className="auth-alert" title={t('auth.accountCreated')} />}

      <Form form={form} layout="vertical" requiredMark onFinish={submit} noValidate
        onFinishFailed={() => setSubmitted(true)}
        validateTrigger={submitted ? ['onChange', 'onBlur'] : 'onBlur'}
        scrollToFirstError={{ focus: true, block: 'center' }}>
        <Form.Item name="username" label={t('auth.login')} extra={t('auth.loginHint')}
          rules={[{ required: true, whitespace: true, message: t('auth.loginRequired') }]}>
          <Input autoComplete="username" inputMode="email" />
        </Form.Item>
        <Form.Item name="password" label={t('auth.password')}
          rules={[{ required: true, message: t('auth.passwordRequired') }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>

        {error && <Alert type="error" showIcon role="alert" className="auth-alert" title={error} />}
        <Button type="primary" htmlType="submit" block loading={sending}
          onClick={() => setSubmitted(true)}>
          {t('auth.submitLogin')}
        </Button>
      </Form>

      <div className="auth-footer">
        <Button type="link" aria-expanded={forgotOpen} aria-controls="forgot-panel"
          onClick={() => setForgotOpen((open) => !open)}>
          {t('auth.forgot')}
        </Button>
        {forgotOpen && <ForgotPassword />}
        <div>
          <Typography.Text>{t('auth.noAccount')}</Typography.Text>{' '}
          <Link to={registerLink}>{t('auth.toRegister')}</Link>
        </div>
      </div>

      <HelpGuide content={{
        title: t('help.loginTitle'),
        steps: (['1', '2', '3', '4', '5'] as const).map((n) => t(`help.loginSteps.${n}`)),
        link: { to: registerLink, label: t('help.toRegister') },
      }} />
    </AuthCard>
  )
}

/** There is no password recovery by e-mail yet: an administrator resets the password. The
 * contacts come from the admin's settings (GET /api/site/contacts), not from the code. */
function ForgotPassword() {
  const { t } = useTranslation()
  const contacts = useSiteContacts()
  const phone = contacts.data?.phone
  const email = contacts.data?.email
  return (
    <Alert id="forgot-panel" type="info" className="forgot-panel"
      title={phone || email ? t('auth.forgotText') : t('auth.forgotNoContacts')}
      description={(
        <>
          {phone && <div>{t('footer.phone')}: <a href={`tel:${phone}`}>{phone}</a></div>}
          {email && <div>{t('footer.email')}: <a href={`mailto:${email}`}>{email}</a></div>}
          <div><AppLink to="/faq#password">{t('auth.forgotMore')}</AppLink></div>
        </>
      )} />
  )
}
