import type { ManagerOrder, ManagerOrderPage, ManagerOrderRow, StaffAction, StaffActionInfo, User } from '../api/types'
import { makeUser } from './fixtures'

// Back-office test data (spec 09), shaped like the API's ManagerOrderOut / ManagerOrderDetailOut.

export const MANAGER: User = makeUser({ id: 701, role: 'manager', last_name: 'Петренко', first_name: 'Іван', email: 'ivan@example.com' })
export const FINANCE: User = makeUser({ id: 702, role: 'finance', last_name: 'Бондар', first_name: 'Ірина' })
export const ADMIN: User = makeUser({ id: 703, role: 'admin', last_name: 'Адмін', first_name: 'Системний' })

export function makeManagerRow(overrides: Partial<ManagerOrderRow> = {}): ManagerOrderRow {
  return {
    id: 42, number: 'TU-2099-000042', status: 'paid', payment_status: 'paid', tour_id: 7,
    tour_title_uk: 'Єгипет, Хургада', hotel_name: 'Coral Bay Resort', start_date: '2099-06-10', end_date: '2099-06-17',
    adults: 2, children: 1, total_uah: '63872.76', client_name: 'Коваленко Олена', client_phone: '+380501234567',
    manager_id: null, manager_name: null, pnr: null, overdue: false, created_at: '2099-01-01T10:00:00Z',
    ...overrides,
  }
}

export function managerPage(items: ManagerOrderRow[], counts = { new: 3, mine: 1, all: 7 }, total = items.length,
  page = 1): ManagerOrderPage {
  return { items, total, page, page_size: 20, queue_counts: counts }
}

export const allowed = (action: StaffAction): StaffActionInfo => ({ action, allowed: true, reason: null })
export const refused = (action: StaffAction, reason: string): StaffActionInfo => ({ action, allowed: false, reason })

export function makeManagerOrder(overrides: Partial<ManagerOrder> = {}): ManagerOrder {
  return {
    ...makeManagerRow(),
    client: { id: 501, last_name: 'Коваленко', first_name: 'Олена', phone: '+380501234567', email: 'olena@example.com' },
    wishes: null, insurance_type_id: 1, insurance_name: 'Базове', transfer_type_id: 1, transfer_name: 'Груповий',
    country_name: 'Єгипет', resort_name: 'Хургада', departure_city_name: 'Київ', transport_type: 'air', meal_plan: 'ai',
    promo_code: null, discount_uah: '0.00', operator_deadline: null, internal_comment: null, reject_reason: null,
    cancel_reason_code: null, cancel_reason: null, fpv_uah: null,
    tourists: [
      { id: 1, last_name_lat: 'KOVALENKO', first_name_lat: 'OLENA', birth_date: '1990-05-14', passport_number: 'FX123456', passport_expiry: '2030-01-01' },
    ],
    payments: [{
      id: 9, type: 'payment', method: 'card', status: 'succeeded', amount_uah: '63872.76', paid_amount: '63872.76',
      received_at: '2099-01-01T10:05:00Z', created_at: '2099-01-01T10:04:00Z', refund_of_id: null, stripe_refund_id: null,
      controller_comment: null,
    }],
    documents: [],
    history: [
      { old_status: null, new_status: 'checkout', changed_by: 501, changed_by_name: 'Коваленко О.', comment: null, changed_at: '2099-01-01T10:00:00Z' },
      { old_status: 'awaiting_payment', new_status: 'paid', changed_by: null, changed_by_name: null, comment: 'Оплату карткою отримано (Stripe)', changed_at: '2099-01-01T10:06:00Z' },
    ],
    staff_actions: [allowed('take'), allowed('assign'), allowed('edit_comment')],
    ...overrides,
  }
}

export const DOCUMENT_RULES = {
  doc_types: ['voucher', 'air_ticket', 'insurance_policy', 'info_sheet'] as const,
  max_documents: 10, max_file_mb: 10, file_types: ['jpg', 'pdf', 'png'],
}
