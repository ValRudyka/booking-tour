// antd Form rules for the personal data fields, shared by registration and the profile form, so
// both check exactly the same (and the same as backend services/users.py, via rules.ts).
import type { Rule } from 'antd/es/form'
import type { Dayjs } from 'dayjs'
import type { TFunction } from 'i18next'
import { isAdult, isValidEmail, nameMatchesCitizenship, NAME_MAX, PASSWORD_MAX, PASSWORD_MIN } from './rules'

type GetFieldValue = (name: string) => unknown

/** Last or first name: required, ≤100, alphabet by the citizenship chosen *now* in the form
 * (`citizenship_id`; Ukraine or nothing chosen = Ukrainian letters). */
export function nameRules(t: TFunction, requiredKey: 'auth.lastNameRequired' | 'auth.firstNameRequired',
  ukraineId: number | undefined): Rule[] {
  return [
    { required: true, whitespace: true, message: t(requiredKey) },
    { max: NAME_MAX, message: t('auth.nameTooLong') },
    ({ getFieldValue }: { getFieldValue: GetFieldValue }) => ({
      validator: (_: unknown, value?: string) => {
        const chosen = getFieldValue('citizenship_id')
        const ukrainian = chosen == null || chosen === ukraineId
        return !value?.trim() || nameMatchesCitizenship(value, ukrainian)
          ? Promise.resolve()
          : Promise.reject(new Error(t(ukrainian ? 'auth.nameUkrainian' : 'auth.nameLatin')))
      },
    }),
  ]
}

export function emailRules(t: TFunction): Rule[] {
  return [
    { required: true, whitespace: true, message: t('auth.emailRequired') },
    { validator: (_, value?: string) => !value?.trim() || isValidEmail(value)
      ? Promise.resolve() : Promise.reject(new Error(t('auth.emailFormat'))) },
  ]
}

/** Required, 18+ by the Kyiv date. */
export function birthDateRules(t: TFunction): Rule[] {
  return [
    { required: true, message: t('auth.birthDateRequired') },
    { validator: (_, value?: Dayjs | null) => !value || isAdult(value)
      ? Promise.resolve() : Promise.reject(new Error(t('auth.notAdult'))) },
  ]
}

/** A new password: 8–128 characters (backend PasswordChange / RegisterRequest). */
export function newPasswordRules(t: TFunction): Rule[] {
  return [
    { required: true, message: t('auth.passwordRequired') },
    { min: PASSWORD_MIN, message: t('auth.passwordTooShort') },
    { max: PASSWORD_MAX, message: t('auth.passwordTooLong') },
  ]
}

/** The repeat field must equal `field`. */
export function repeatRules(t: TFunction, field: string): Rule[] {
  return [
    { required: true, message: t('auth.passwordRepeatRequired') },
    ({ getFieldValue }: { getFieldValue: GetFieldValue }) => ({
      validator: (_: unknown, value?: string) => !value || value === getFieldValue(field)
        ? Promise.resolve() : Promise.reject(new Error(t('auth.passwordMismatch'))),
    }),
  ]
}
