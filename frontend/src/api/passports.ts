import { api } from './client'
import type { SavedPassport, SavedPassportIn } from './types'

// Saved tourists (backend routers/passports.py, ТЗ form 4.6.1.1, field 8). The list itself is
// useSavedPassports() in api/orders.ts (query key ['me', 'passports']), shared with the booking.
export const PASSPORTS_KEY = ['me', 'passports'] as const

/** A new passport (POST) or all fields of a saved one (PUT). Field rules answer 422 with `loc`
 * (type "profile_rule"), the same number twice 409 with `loc` ["body", "passport_number"]. */
export async function savePassport(data: SavedPassportIn, id?: number): Promise<SavedPassport> {
  return id === undefined
    ? (await api.post<SavedPassport>('/me/passports', data)).data
    : (await api.put<SavedPassport>(`/me/passports/${id}`, data)).data
}

export async function deletePassport(id: number): Promise<void> {
  await api.delete(`/me/passports/${id}`)
}
