// Data builders for the admin pages (spec 13). The shapes are the generated API types, so a backend
// change that the pages depend on fails type-checking here first.
import type {
  AdminSettings, AdminUser, AuditEntry, CountryAdmin, HotelAdmin, ReferenceAction, ReferenceActionInfo, ResortAdmin,
  ServiceTypeAdmin, UserActionInfo, UserAdminAction,
} from '../api/types'
import { ADMIN } from './officeFixtures'

export const userAllowed = (action: UserAdminAction): UserActionInfo => ({ action, allowed: true, reason: null })
export const userRefused = (action: UserAdminAction, reason: string): UserActionInfo => ({ action, allowed: false, reason })
export const refAllowed = (action: ReferenceAction): ReferenceActionInfo => ({ action, allowed: true, reason: null })
export const refRefused = (action: ReferenceAction, reason: string): ReferenceActionInfo => ({ action, allowed: false, reason })

export const ALL_USER_ACTIONS: UserActionInfo[] = ['edit', 'change_role', 'block', 'reset_password'].map(
  (action) => userAllowed(action as UserAdminAction))

export function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 810, phone: '+380671112233', email: 'olena.koval@tour.ua', role: 'manager', last_name: 'Коваль',
    first_name: 'Олена', birth_date: null, citizenship_id: null, loyalty_points: 0, is_active: true,
    created_at: '2026-11-02T09:00:00Z', updated_at: '2026-11-20T12:30:00Z', user_actions: ALL_USER_ACTIONS,
    ...overrides,
  }
}

/** The signed-in admin as the users list shows them: the rules refuse acting on yourself. */
export const ADMIN_ROW: AdminUser = makeAdminUser({
  ...ADMIN, updated_at: '2026-11-20T12:30:00Z',
  user_actions: [userAllowed('edit'), userRefused('change_role', 'Не можна змінити власну роль'),
    userRefused('block', 'Не можна заблокувати себе'),
    userRefused('reset_password', 'Власний пароль змініть через «Змінити пароль» у меню профілю')],
})

export function usersPage(items: AdminUser[], total = items.length, page = 1) {
  return { items, total, page, page_size: 20 }
}

const ARCHIVABLE = [refAllowed('edit'), refAllowed('archive'), refAllowed('delete')]

export function makeCountry(overrides: Partial<CountryAdmin> = {}): CountryAdmin {
  return { id: 1, iso_code: 'TR', name_uk: 'Туреччина', name_en: 'Turkey', is_archived: false, admin_actions: ARCHIVABLE, ...overrides }
}

export function makeResort(overrides: Partial<ResortAdmin> = {}): ResortAdmin {
  return { id: 11, country_id: 1, name_uk: 'Кемер', name_en: 'Kemer', is_archived: false, admin_actions: ARCHIVABLE, ...overrides }
}

export function makeHotelAdmin(overrides: Partial<HotelAdmin> = {}): HotelAdmin {
  return {
    id: 21, resort_id: 11, name: 'Sea Breeze', stars: 5, description: null, beach_line: 1, distance_to_beach_m: 50,
    distance_to_airport_km: 60, check_in: '14:00:00', check_out: '12:00:00', amenities: ['Басейн'], room_types: [],
    rating_avg: '4.50', is_archived: false, admin_actions: ARCHIVABLE, ...overrides,
  }
}

export function makeServiceType(overrides: Partial<ServiceTypeAdmin> = {}): ServiceTypeAdmin {
  return { id: 31, name_uk: 'Базове', price_uah: '350.00', is_default: true, is_archived: false,
    admin_actions: [refAllowed('edit'), refRefused('archive', 'Типовий запис не архівується — спершу призначте типовим інший'),
      refRefused('delete', 'Типовий запис не видаляється — спершу призначте типовим інший')], ...overrides }
}

export function makeSettings(overrides: Partial<AdminSettings> = {}): AdminSettings {
  return {
    eur_rate: '48.5000', usd_rate: '41.2000', acquiring_percent: '2.5', booking_timeout_min: 20,
    bank_transfer_hold_hours: 48, review_premoderation: true, system_email: 'noreply@tour.ua', maintenance_mode: false,
    support_phone: '+380441234567', support_email: 'help@tour.ua', support_address: '', maintenance_message: '',
    uah_rate: '1',
    changes: { booking_timeout_min: { updated_at: '2026-11-20T10:00:00Z', updated_by: 703, updated_by_name: 'Адмін Системний' } },
    rules: {
      eur_rate: { min: '0.0001', max: '10000', places: 4, max_length: null },
      usd_rate: { min: '0.0001', max: '10000', places: 4, max_length: null },
      acquiring_percent: { min: '0', max: '10', places: 2, max_length: null },
      booking_timeout_min: { min: '5', max: '120', places: 0, max_length: null },
      bank_transfer_hold_hours: { min: '1', max: '168', places: 0, max_length: null },
      system_email: { min: null, max: null, places: null, max_length: 255 },
      support_email: { min: null, max: null, places: null, max_length: 255 },
      support_address: { min: null, max: null, places: null, max_length: 300 },
      maintenance_message: { min: null, max: null, places: null, max_length: 500 },
    },
    limits: { max_review_photos: 10, max_review_photo_mb: 5 },
    ...overrides,
  }
}

export function makeAuditEntry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 901, user_id: 703, entity: 'user', entity_id: '810', action: 'role_changed',
    old_value: { role: 'manager' }, new_value: { role: 'finance' }, created_at: '2026-11-24T08:15:00Z',
    user_name: 'Адмін Системний', user_role: 'admin', ...overrides,
  }
}
