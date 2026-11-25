import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { PASSWORD_MAX, PASSWORD_MIN } from './rules'
import './PasswordRules.css'

/** Password requirements: exactly what the backend checks (8–128 characters), nothing invented.
 * Shared by registration and the password change in the profile. */
export function PasswordRules({ value }: { value: string }) {
  const { t } = useTranslation()
  const rules = [
    { label: t('auth.ruleMin'), met: value.length >= PASSWORD_MIN },
    { label: t('auth.ruleMax'), met: value.length <= PASSWORD_MAX },
  ]
  return (
    <ul className="password-rules" aria-label={t('auth.passwordRules')} aria-live="polite">
      {rules.map((rule) => (
        <li key={rule.label} className={rule.met ? 'rule-met' : 'rule-not-met'}>
          {rule.met ? <CheckOutlined aria-hidden /> : <CloseOutlined aria-hidden />}
          <span>{rule.label} <span className="visually-hidden">({t(rule.met ? 'auth.ruleMet' : 'auth.ruleNotMet')})</span></span>
        </li>
      ))}
    </ul>
  )
}
