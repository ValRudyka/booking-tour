import { Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { changePassword } from '../../api/profile'
import { mapFormError } from '../../features/auth/authErrors'
import { newPasswordRules, repeatRules } from '../../features/auth/formRules'
import { PasswordRules } from '../../features/auth/PasswordRules'
import { useAuth } from '../../features/auth/useAuth'
import { FormModal } from './FormModal'

interface Values {
  current_password: string
  new_password: string
  new_password_repeat: string
}

const FIELDS = ['current_password', 'new_password'] as const

/**
 * «Змінити пароль» for staff (office user menu; spec 13 additions). The same request, rules and
 * ending as the client's profile (spec 08, pages/cabinet/ProfilePage.tsx PasswordCard, which is
 * not a shared component, so its pieces are reused here): POST /auth/me/password ends every
 * session on the server, this one too, so the user is sent to /login to sign in again.
 */
export function StaffPasswordModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { endSessionAfterPasswordChange } = useAuth()
  const [form] = Form.useForm<Values>()
  const value = Form.useWatch('new_password', form) ?? ''
  const [sending, setSending] = useState(false)
  const [alert, setAlert] = useState<string | null>(null)

  const submit = async (values: Values) => {
    setAlert(null)
    setSending(true)
    try {
      await changePassword({ current_password: values.current_password, new_password: values.new_password })
    } catch (err) {
      const mapped = mapFormError(err, FIELDS)
      form.setFields(mapped.fields as Parameters<typeof form.setFields>[0])
      setAlert(mapped.alert)
      setSending(false)
      return false
    }
    endSessionAfterPasswordChange()
    return false                       // the page changes to /login; nothing to close
  }

  return (
    <FormModal open={open} title={t('admin.password.title')} okText={t('cabinet.profile.changePassword')}
      cancelText={t('admin.cancel')} busy={sending} error={alert} form={form}
      onCancel={() => { setAlert(null); onClose() }} onSubmit={submit}>
      <Typography.Paragraph type="secondary">{t('cabinet.profile.passwordNote')}</Typography.Paragraph>
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
    </FormModal>
  )
}
