// Backend errors -> what the auth forms show. One table, so every page says the same thing:
// - an error about a field goes under that field (form.setFields);
// - an error about the whole request goes in the Alert above the submit button;
// - backend texts are never shown as they are: they are English (pydantic), technical, or
//   phrased for the API. A text that is not in this table becomes the generic message.
import type { ParseKeys } from 'i18next'
import i18n from '../../i18n'
import { ApiError, type FieldIssue } from '../../api/client'

export interface FieldError {
  name: string
  errors: string[]
}

export interface MappedError {
  fields: FieldError[]
  /** Text for the Alert, or null when everything went under fields. */
  alert: string | null
}

const t = (key: ParseKeys): string => i18n.t(key)

/** Known plain `detail` texts of the backend (services/users.py) -> fields and our wording. */
function knownDetail(detail: string): FieldError[] | null {
  const rules: [RegExp, () => FieldError[]][] = [
    [/^Користувач з таким телефоном вже існує$/, () => [{ name: 'phone', errors: [t('auth.phoneTaken')] }]],
    [/^Користувач з таким e-mail вже існує$/, () => [{ name: 'email', errors: [t('auth.emailTaken')] }]],
    [/^Прізвище та ім'я потрібно вводити українською мовою$/, () => [
      { name: 'last_name', errors: [t('auth.nameUkrainian')] },
      { name: 'first_name', errors: [t('auth.nameUkrainian')] }]],
    [/^Прізвище та ім'я потрібно вводити латиницею$/, () => [
      { name: 'last_name', errors: [t('auth.nameLatin')] },
      { name: 'first_name', errors: [t('auth.nameLatin')] }]],
    [/^Невідома країна громадянства$/, () => [{ name: 'citizenship_id', errors: [t('auth.citizenshipUnknown')] }]],
    [/^Реєстрація доступна лише з 18 років$/, () => [{ name: 'birth_date', errors: [t('auth.notAdult')] }]],
  ]
  const hit = rules.find(([pattern]) => pattern.test(detail))
  return hit ? hit[1]() : null
}

/** One 422 issue -> a Ukrainian text for its field. */
function issueText(field: string, issue: FieldIssue): string {
  // Our own backend validators already speak Ukrainian: "Value error, Телефон у міжнародному…".
  const own = issue.msg.replace(/^Value error, /, '')
  if (issue.type === 'value_error' && /[А-ЩЬЮЯҐЄІЇа-щьюяґєії]/.test(own)) return own
  if (issue.type === 'missing') {
    const required: Record<string, string> = {
      phone: t('auth.phoneRequired'), email: t('auth.emailRequired'), password: t('auth.passwordRequired'),
      last_name: t('auth.lastNameRequired'), first_name: t('auth.firstNameRequired'),
      birth_date: t('auth.birthDateRequired'), citizenship_id: t('auth.citizenshipRequired'),
      consent: t('auth.consentRequired'),
    }
    return required[field] ?? t('auth.required')
  }
  if (field === 'password') {
    if (issue.type === 'string_too_short') return t('auth.passwordTooShort')
    if (issue.type === 'string_too_long') return t('auth.passwordTooLong')
  }
  if (field === 'last_name' || field === 'first_name') {
    if (issue.type === 'string_too_short') return t(field === 'last_name' ? 'auth.lastNameRequired' : 'auth.firstNameRequired')
    if (issue.type === 'string_too_long') return t('auth.nameTooLong')
  }
  if (field === 'email') return t('auth.emailFormat')
  if (field === 'phone') return t('auth.phoneFormat')
  if (field === 'birth_date') return t('auth.birthDateInvalid')
  if (field === 'citizenship_id') return t('auth.citizenshipUnknown')
  return t('auth.checkField')
}

/** The Alert text for an error that is not about one field. */
export function requestErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return t('errors.generic')
  switch (error.kind) {
    case 'maintenance': return error.message          // the API's own maintenance text
    case 'network': return t('errors.network')
    case 'server': return t('errors.server')
    case 'rate_limited': return t('auth.tooManyAttempts')
    default: return t('errors.generic')
  }
}

/** POST /auth/login: a 401 is always «wrong login or password» (the backend does not say which,
 * and a blocked account looks the same, on purpose). */
export function loginErrorText(error: unknown): string {
  if (error instanceof ApiError && error.kind === 'unauthorized') return t('auth.wrongCredentials')
  return requestErrorText(error)
}

/** POST /auth/register: field errors where possible, else one Alert text. */
export function mapRegisterError(error: unknown, formFields: readonly string[]): MappedError {
  if (error instanceof ApiError) {
    if (error.issues.length > 0) {
      const byField = new Map<string, string[]>()
      let unplaced = false
      for (const issue of error.issues) {
        const field = issue.loc[0] === 'body' ? String(issue.loc[1] ?? '') : ''
        if (!formFields.includes(field)) {
          unplaced = true
          continue
        }
        byField.set(field, [...(byField.get(field) ?? []), issueText(field, issue)])
      }
      return { fields: [...byField].map(([name, errors]) => ({ name, errors: [...new Set(errors)] })),
        alert: unplaced ? t('errors.generic') : null }
    }
    if (error.detail) {
      const fields = knownDetail(error.detail)
      if (fields) return { fields, alert: null }
    }
  }
  return { fields: [], alert: requestErrorText(error) }
}
