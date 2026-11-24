import type { AxiosResponse } from 'axios'
import { vi } from 'vitest'
import { api } from '../api/client'
import type { City, Country, Resort, TourCard, TourPage } from '../api/types'

export const COUNTRIES: Country[] = [
  { id: 1, iso_code: 'EG', name_uk: 'Єгипет', name_en: 'Egypt' },
  { id: 2, iso_code: 'TR', name_uk: 'Туреччина', name_en: 'Turkey' },
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
