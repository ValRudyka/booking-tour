import { api } from './client'
import type { PasswordChange, ProfileUpdate, User } from './types'

/** PATCH /auth/me: only the fields sent change. Field rules answer 422 with `loc`
 * (type "profile_rule"), an e-mail already in use 409 with `loc` ["body", "email"]. */
export async function updateProfile(data: ProfileUpdate): Promise<User> {
  return (await api.patch<User>('/auth/me', data)).data
}

/** POST /auth/me/password: 204. The backend then refuses every token issued before it, the one
 * of this tab included, so the caller signs out (AuthContext.endSessionAfterPasswordChange). */
export async function changePassword(data: PasswordChange): Promise<void> {
  await api.post('/auth/me/password', data)
}
