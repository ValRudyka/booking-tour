import type { FormInstance } from 'antd'
import { useEffect } from 'react'
import type { ApiError } from '../../../api/client'
import { mapFormError } from '../../../features/auth/authErrors'

/**
 * Field errors of an admin dialog (spec 03 §2a): a 422 with `loc` (Pydantic: phone format, password
 * length…) goes under its field through the shared mapFormError(); a plain-text refusal (409 «вже
 * зареєстровано», the service's 422 texts) stays in the dialog's Alert (actionErrorText).
 */
export function useFieldIssues(form: FormInstance, error: ApiError | null, fields: readonly string[]) {
  useEffect(() => {
    if (!error || error.issues.length === 0) return
    const mapped = mapFormError(error, fields)
    form.setFields(mapped.fields as Parameters<typeof form.setFields>[0])
  }, [error, form, fields])
}

