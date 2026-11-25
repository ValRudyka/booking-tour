import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type {
  AdminSettings, AdminUser, AdminUserPage, AdminUsersQuery, AuditLogQuery, AuditPage, CityAdmin, CountryAdmin,
  GatewayStatus, HotelAdmin, Language, ResortAdmin, ServiceTypeAdmin, SettingsIn, StaffCreate, StaffCreated,
  UserPatch,
} from './types'

// Administration (spec 13; backend routers/admin_users.py, admin_reference.py, admin_settings.py).
// Every user and reference record carries the actions the admin may take with it
// (user_actions / admin_actions, services/admin_actions.py): the pages show only those.
// These are the admin's own lists, archived records included. The tour editor (spec 10) uses the
// public /api/reference/* lists, which hide archived records.

export type ReferenceKind = 'countries' | 'cities' | 'resorts' | 'hotels' | 'insurance-types' | 'transfer-types'

export interface ReferenceItemOf {
  countries: CountryAdmin
  cities: CityAdmin
  resorts: ResortAdmin
  hotels: HotelAdmin
  'insurance-types': ServiceTypeAdmin
  'transfer-types': ServiceTypeAdmin
}

export const adminKeys = {
  all: ['admin'] as const,
  users: ['admin', 'users'] as const,
  user: (id: number) => ['admin', 'users', id] as const,
  reference: (kind: ReferenceKind) => ['admin', 'reference', kind] as const,
  languages: ['admin', 'languages'] as const,
  settings: ['admin', 'settings'] as const,
  gateway: ['admin', 'payment-gateway'] as const,
  audit: ['admin', 'audit-log'] as const,
}

export function useAdminUsers(query: AdminUsersQuery, enabled = true) {
  return useQuery({
    queryKey: [...adminKeys.users, query],
    queryFn: async () => (await api.get<AdminUserPage>('/admin/users', { params: query })).data,
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useAdminUser(id: number | null) {
  return useQuery({
    queryKey: adminKeys.user(id ?? 0),
    queryFn: async () => (await api.get<AdminUser>(`/admin/users/${id}`)).data,
    enabled: id !== null,
    staleTime: 0,
  })
}

/** The whole list of a reference kind, archived records included (the API does not paginate it). */
export function useReferenceList<K extends ReferenceKind>(kind: K, enabled = true) {
  return useQuery({
    queryKey: adminKeys.reference(kind),
    queryFn: async () => (await api.get<ReferenceItemOf[K][]>(`/admin/${kind}`)).data,
    enabled,
  })
}

export function useLanguages() {
  return useQuery({
    queryKey: adminKeys.languages,
    queryFn: async () => (await api.get<Language[]>('/admin/languages')).data,
  })
}

/** Also read by OfficeLayout for the maintenance Alert (admins only). */
export function useAdminSettings(enabled = true) {
  return useQuery({
    queryKey: adminKeys.settings,
    queryFn: async () => (await api.get<AdminSettings>('/admin/settings')).data,
    enabled,
    staleTime: 30_000,
  })
}

export function useGatewayStatus() {
  return useQuery({
    queryKey: adminKeys.gateway,
    queryFn: async () => (await api.get<GatewayStatus>('/admin/payment-gateway')).data,
    staleTime: 5 * 60_000,
  })
}

export function useAuditLog(query: AuditLogQuery) {
  return useQuery({
    queryKey: [...adminKeys.audit, query],
    queryFn: async () => (await api.get<AuditPage>('/admin/audit-log', { params: query })).data,
    placeholderData: keepPreviousData,
    staleTime: 0,
  })
}

// ---------- actions
export const adminUsersApi = {
  /** Without `password` the server generates a temporary one and answers it once. */
  create: async (body: Omit<StaffCreate, 'password'>) => (await api.post<StaffCreated>('/admin/users', body)).data,
  update: async (id: number, body: UserPatch) => (await api.patch<AdminUser>(`/admin/users/${id}`, body)).data,
  resetPassword: async (id: number, newPassword: string) =>
    (await api.post<AdminUser>(`/admin/users/${id}/reset-password`, { new_password: newPassword })).data,
}

export const referenceApi = {
  create: async <K extends ReferenceKind>(kind: K, body: object) =>
    (await api.post<ReferenceItemOf[K]>(`/admin/${kind}`, body)).data,
  update: async <K extends ReferenceKind>(kind: K, id: number, body: object) =>
    (await api.patch<ReferenceItemOf[K]>(`/admin/${kind}/${id}`, body)).data,
  archive: async <K extends ReferenceKind>(kind: K, id: number) =>
    (await api.post<ReferenceItemOf[K]>(`/admin/${kind}/${id}/archive`)).data,
  restore: async <K extends ReferenceKind>(kind: K, id: number) =>
    (await api.post<ReferenceItemOf[K]>(`/admin/${kind}/${id}/restore`)).data,
  remove: async (kind: ReferenceKind, id: number) => { await api.delete(`/admin/${kind}/${id}`) },
}

export const languagesApi = {
  create: async (body: { code: string; name: string; is_enabled: boolean }) =>
    (await api.post<Language>('/admin/languages', body)).data,
  update: async (code: string, body: { name?: string; is_enabled?: boolean }) =>
    (await api.patch<Language>(`/admin/languages/${code}`, body)).data,
  remove: async (code: string) => { await api.delete(`/admin/languages/${code}`) },
}

/** Only the fields sent change (PUT /admin/settings). */
export async function saveSettings(body: SettingsIn): Promise<AdminSettings> {
  return (await api.put<AdminSettings>('/admin/settings', body)).data
}
