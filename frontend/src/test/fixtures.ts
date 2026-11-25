import { AxiosError, type AxiosResponse } from 'axios'
import { vi } from 'vitest'
import { api } from '../api/client'
import type {
  City, Country, HotelDetail, OrderWithPrice, Price, PublicReview, Resort, ReviewPage, TourCard, TourDetail,
  TourPage, User,
} from '../api/types'
import { TOKEN_KEY } from '../features/auth/tokenStorage'

export const COUNTRIES: Country[] = [
  { id: 1, iso_code: 'EG', name_uk: 'Єгипет', name_en: 'Egypt' },
  { id: 2, iso_code: 'TR', name_uk: 'Туреччина', name_en: 'Turkey' },
  { id: 3, iso_code: 'UA', name_uk: 'Україна', name_en: 'Ukraine' },
]
export const RESORTS: Resort[] = [
  { id: 10, country_id: 1, name_uk: 'Хургада', name_en: 'Hurghada' },
  { id: 20, country_id: 2, name_uk: 'Анталія', name_en: 'Antalya' },
]
export const CITIES: City[] = [
  { id: 100, country_id: 99, name_uk: 'Київ', name_en: 'Kyiv', iata_code: 'KBP' },
]

let nextId = 1
export function makeTour(overrides: Partial<TourCard> = {}): TourCard {
  const id = nextId++
  return {
    id,
    title_uk: `Coral Bay Resort, Хургада ${id}`,
    title_en: `Coral Bay Resort, Hurghada ${id}`,
    country: COUNTRIES[0],
    resort: RESORTS[0],
    hotel: { id: 5, resort_id: 10, name: 'Coral Bay Resort', stars: 5, rating_avg: '4.60' },
    transport_type: 'air',
    departure_city: CITIES[0],
    departure_from: '2099-06-01',
    departure_to: '2099-06-30',
    nights: 7,
    currency: 'EUR',
    base_price: '700.00',
    price_from_uah: '32000.00',
    free_seats: 10,
    is_featured: false,
    meal_plan: null,
    image_url: null,
    ...overrides,
  }
}

export function page(items: TourCard[], total = items.length, pageNumber = 1): TourPage {
  return { items, total, page: pageNumber, page_size: 12 }
}

type Handler = (params: Record<string, unknown>) => unknown

/**
 * Replaces the API client's GET with canned answers by path. A handler may return data or
 * throw (e.g. an ApiError) like the real interceptor would. Returns the spy so tests can check
 * the parameters that were sent.
 */
export function mockApi(tours: Handler, extra: Record<string, Handler> = {}) {
  const handlers: Record<string, Handler> = {
    '/tours': tours,
    '/reference/countries': () => COUNTRIES,
    '/reference/resorts': (params) => RESORTS.filter((r) => r.country_id === params.country_id),
    '/reference/cities': () => CITIES,
    '/site/contacts': () => ({ phone: null, email: null }),
    ...extra,
  }
  return vi.spyOn(api, 'get').mockImplementation(async (url: string, config?: { params?: unknown }) => {
    const handler = handlers[url]
    if (!handler) throw new Error(`Unexpected GET ${url}`)
    const data = await handler((config?.params ?? {}) as Record<string, unknown>)
    return { data, status: 200 } as AxiosResponse
  })
}

/** The params of the last GET /tours call. */
export function lastToursParams(spy: ReturnType<typeof mockApi>): Record<string, unknown> {
  const calls = spy.mock.calls.filter(([url]) => url === '/tours')
  const config = calls.at(-1)?.[1] as { params?: Record<string, unknown> } | undefined
  if (!config?.params) throw new Error('GET /tours was not called with params')
  return config.params
}

export const HOTEL_FACTS = {
  beach_line: 1, distance_to_beach_m: 0, distance_to_airport_km: 12,
  check_in: '14:00:00', check_out: '12:00:00',
  amenities: ['Власний пляж', 'SPA-центр'], room_types: ['Стандартний номер', 'Сімейний номер'],
}
const NO_FACTS = {
  beach_line: null, distance_to_beach_m: null, distance_to_airport_km: null, check_in: null,
  check_out: null, amenities: [], room_types: [],
}

/** GET /api/tours/{id}: a card plus the page fields. Hotel facts empty unless `hotelFacts`. */
export function makeTourDetail(overrides: Partial<TourDetail> = {},
  hotelFacts: Partial<HotelDetail> = {}): TourDetail {
  const card = makeTour()
  return {
    ...card,
    hotel: { ...card.hotel, ...NO_FACTS, ...hotelFacts },
    child_price: '350.00',
    child_price_uah: '16000.00',
    flight_out: 'DM 1101', flight_back: 'DM 1102',
    description: 'Тиждень на Червоному морі.',
    included: ['Авіапереліт', 'Проживання'],
    excluded: ['Медичне страхування — обирається під час бронювання'],
    hotel_description: 'Готель на першій лінії.',
    program_days: [{ day_number: 1, description: 'Переліт і заселення.' },
      { day_number: 2, description: 'Відпочинок на пляжі.' }],
    images: [],
    reviews_count: 0,
    service_rating_avg: null,
    ...overrides,
  }
}

export function makeReview(overrides: Partial<PublicReview> = {}): PublicReview {
  const id = nextId++
  return {
    id, author: 'Олена К.', tour_id: 1, tour_title_uk: 'Тур', hotel_name: 'Coral Bay Resort',
    trip_month: '2026-10', published_at: '2026-10-20T10:00:00Z', hotel_rating: 5, service_rating: 4,
    positive: 'Чудовий готель.', negative: null, photos: [], ...overrides,
  }
}

export function reviewPage(items: PublicReview[], total = items.length, pageNumber = 1): ReviewPage {
  return { items, total, page: pageNumber, page_size: 10 }
}

export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 501, phone: '+380501234567', email: 'olena@example.com', role: 'client',
    last_name: 'Коваленко', first_name: 'Олена', birth_date: '1990-05-14', citizenship_id: 3,
    loyalty_points: 0, is_active: true, created_at: '2026-11-01T10:00:00Z', ...overrides,
  }
}

/** A signed-in visitor for a test: a stored token and GET /auth/me answering with `user`.
 * Pass the result to mockApi's `extra` handlers. */
export function signIn(user: User = makeUser()): Record<string, () => User> {
  window.localStorage.setItem(TOKEN_KEY, 'test-token')
  return { '/auth/me': () => user }
}

// ---------- a fake backend at the axios adapter level: unlike mockApi, the real interceptors run
// (token header, 401 handling), which the auth tests need.
export interface FakeRequest {
  method: string
  url: string
  params: Record<string, unknown>
  /** JSON body as an object, or a form body (login) as URLSearchParams. */
  body: unknown
  authorization: string | null
}
type Route = (request: FakeRequest) => [number, unknown]

export function mockServer(routes: Record<string, Route>) {
  const calls: FakeRequest[] = []
  const all: Record<string, Route> = {
    'GET /site/contacts': () => [200, { phone: null, email: null }],
    'GET /reference/countries': () => [200, COUNTRIES],
    'GET /reference/cities': () => [200, CITIES],
    'GET /tours': () => [200, page([])],
    ...routes,
  }
  api.defaults.adapter = async (config) => {
    const method = (config.method ?? 'get').toUpperCase()
    const url = config.url ?? ''
    const raw = config.data
    const body = typeof raw === 'string'
      ? (raw.startsWith('{') ? JSON.parse(raw) : new URLSearchParams(raw))
      : raw instanceof URLSearchParams ? raw : raw ?? null
    const headers = config.headers as unknown as { get?: (name: string) => unknown }
    const authorization = (headers.get?.('Authorization') as string | undefined) ?? null
    const request = { method, url, params: (config.params ?? {}) as Record<string, unknown>, body, authorization }
    calls.push(request)
    const route = all[`${method} ${url}`]
    if (!route) throw new Error(`Unexpected ${method} ${url}`)
    const [status, data] = route(request)
    const response = { data, status, statusText: '', headers: {}, config }
    if (status >= 400) {
      throw new AxiosError(`HTTP ${status}`, status >= 500 ? 'ERR_BAD_RESPONSE' : 'ERR_BAD_REQUEST',
        config, null, response)
    }
    return response
  }
  return calls
}

// ---------- checkout and payment
export function makePrice(overrides: Partial<Price> = {}): Price {
  return {
    adults: 2, children: 0, currency: 'EUR', base_price: '700.00', child_price: '350.00', rate: '45.1234',
    tour_uah: '63172.76', insurance_id: 1, insurance_name: 'Базове', insurance_per_tourist_uah: '350.00',
    insurance_uah: '700.00', transfer_id: 5, transfer_name: 'Груповий', transfer_uah: '0.00',
    subtotal_uah: '63872.76', promo_code: null, discount_uah: '0.00', total_uah: '63872.76', ...overrides,
  }
}

export const TOURISTS = [
  { id: 11, last_name_lat: 'KOVALENKO', first_name_lat: 'OLENA', birth_date: '1990-05-14', passport_number: 'FX123456', passport_expiry: '2105-01-01' },
  { id: 12, last_name_lat: 'KOVALENKO', first_name_lat: 'IVAN', birth_date: '1988-02-01', passport_number: 'FX654321', passport_expiry: '2105-01-01' },
]

/** An order of the checkout (booking wizard, payment pages): tour 7, hold for 15 more minutes. */
export function makeCheckoutOrder(overrides: Partial<OrderWithPrice> = {}): OrderWithPrice {
  return {
    id: 1, number: 'TU-2099-000001', status: 'checkout', payment_status: 'awaiting', tour_id: 7,
    tour_title_uk: 'Coral Bay Resort, Хургада', hotel_name: 'Coral Bay Resort', start_date: '2099-06-10', end_date: '2099-06-17',
    adults: 2, children: 0, insurance_type_id: 1, transfer_type_id: 5, promo_code: null, wishes: null,
    total_uah: '63872.76', discount_uah: '0.00', rate_used: '45.1234',
    hold_expires_at: new Date(Date.now() + 15 * 60_000).toISOString(), offer_accepted_at: null, pnr: null,
    reject_reason: null, cancel_reason_code: null, cancel_reason: null, fpv_uah: null,
    created_at: new Date().toISOString(), tourists: [], history: [], payments: [], price: makePrice(), ...overrides,
  }
}
