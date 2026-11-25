import type {
  Hotel, ManagerOrder, ManagerOrderPage, ManagerOrderRow, ManagerTour, ManagerTourPage, ManagerTourRow, StaffAction, StaffActionInfo,
  TourAction, TourActionInfo, TourRules, User,
} from '../api/types'
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

// ---------- tours (spec 10), shaped like ManagerTourOut / ManagerTourListItem / TourRulesOut
export const tourAllowed = (action: TourAction): TourActionInfo => ({ action, allowed: true, reason: null })
export const tourRefused = (action: TourAction, reason: string): TourActionInfo => ({ action, allowed: false, reason })

export const DRAFT_ACTIONS: TourActionInfo[] = [tourAllowed('edit'), tourAllowed('publish'), tourAllowed('archive'), tourAllowed('copy')]
export const ACTIVE_ACTIONS: TourActionInfo[] = [
  tourRefused('edit', 'Редагувати можна лише чернетку — спершу зніміть тур з публікації'),
  tourAllowed('unpublish'), tourAllowed('archive'), tourAllowed('copy'),
]

export const HOTELS: Hotel[] = [
  { id: 300, resort_id: 10, name: 'Coral Bay Resort', stars: 5, rating_avg: null },
  { id: 301, resort_id: 10, name: 'Sunrise Garden', stars: 4, rating_avg: null },
  { id: 400, resort_id: 20, name: 'Antalya Palace', stars: 5, rating_avg: null },
]

export const TOUR_RULES: TourRules = {
  photos: { max_files: 20, max_file_mb: 5, file_types: ['jpg', 'png'] },
  max_title: 200, max_description: 5000, max_day_text: 2000, min_nights: 1, max_nights: 30,
  max_list_items: 20, max_list_item_length: 200,
}

export function makeManagerTour(overrides: Partial<ManagerTour> = {}): ManagerTour {
  return {
    id: 7, status: 'draft', title_uk: 'Coral Bay, Хургада', title_en: 'Coral Bay, Hurghada', hotel_id: 300,
    hotel: { id: 300, name: 'Coral Bay Resort', stars: 5, resort_id: 10, resort_name: 'Хургада', country_id: 1, country_name: 'Єгипет', is_archived: false },
    transport_type: 'air', departure_city_id: 100, flight_out: 'PQ 7121', flight_back: null,
    departure_from: '2099-06-01', departure_to: '2099-06-20', nights: 7, seats_total: 20, seats_sold: 0, seats_held: 0,
    base_price: '850.00', child_price: null, currency: 'EUR', description: 'Відпочинок на Червоному морі', is_featured: false,
    meal_plan: 'ai', included: ['Авіапереліт'], excluded: [], created_by: 701,
    created_at: '2099-01-01T10:00:00Z', updated_at: '2099-01-01T10:00:00Z',
    program_days: [{ day_number: 1, description: 'Приліт' }, { day_number: 2, description: 'Пляж' }],
    images: [],
    tour_actions: DRAFT_ACTIONS, locked_fields: [], active_bookings: 0, archive_cancels: 0, for_sale: false,
    ...overrides,
  }
}

export function makeTourRow(overrides: Partial<ManagerTourRow> = {}): ManagerTourRow {
  return {
    id: 7, status: 'active', title_uk: 'Coral Bay, Хургада', hotel_id: 300, hotel_name: 'Coral Bay Resort',
    resort_name: 'Хургада', country_name: 'Єгипет', image_url: null, departure_from: '2099-06-01', departure_to: '2099-06-20',
    nearest_start: '2099-06-01', nights: 7, seats_total: 20, seats_sold: 2, free_seats: 16, base_price: '850.00', currency: 'EUR',
    is_featured: false, updated_at: '2099-01-01T10:00:00Z',
    tour_actions: ACTIVE_ACTIONS, locked_fields: [], active_bookings: 0, archive_cancels: 0, for_sale: true,
    ...overrides,
  }
}

export function tourPage(items: ManagerTourRow[], total = items.length, page = 1): ManagerTourPage {
  return { items, total, page, page_size: 20 }
}
