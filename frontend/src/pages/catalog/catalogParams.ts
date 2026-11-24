// Catalog state <-> URL query string <-> GET /api/tours parameters.
//
// The URL is the single source of truth (spec §4 "Поведінка"): filters, sort and page live in
// ?country_id=3&stars=4&stars=5&page=2, so a link opens the same results in a new tab and the
// browser's Back button restores the previous search. The URL keys are the API's own parameter
// names, so the mapping is 1:1. Everything read from the URL is validated here: a hand-edited
// or outdated link is cleaned up instead of causing a 422 from the API.
import type { TourSearchParams, TourSort, TransportType } from '../../api/types'

export const PAGE_SIZE = 12
/** Sorts the catalog offers (spec §4); the API also has date_desc, which is not offered. */
export const SORTS = ['date_asc', 'price_asc', 'price_desc', 'rating_desc'] as const satisfies readonly TourSort[]
export type CatalogSort = (typeof SORTS)[number]
export const DEFAULT_SORT: CatalogSort = 'date_asc' // = the API's default: nearest departure first
export const STAR_OPTIONS = [3, 4, 5] as const
export const TRANSPORT_TYPES: readonly TransportType[] = ['air', 'bus', 'none']
export const NIGHTS_MIN = 1
export const NIGHTS_MAX = 30 // form 4.6.2.1, field 11
const Q_MAX_LENGTH = 100 // the API's limit

export interface CatalogFilters {
  q?: string
  country_id?: number
  resort_id?: number
  departure_city_id?: number
  transport_type?: TransportType
  date_from?: string
  date_to?: string
  nights_min?: number
  nights_max?: number
  /** Whole hryvnias; sent as is, never used for arithmetic. */
  price_min?: number
  price_max?: number
  stars: number[]
  has_seats?: boolean
}

export interface CatalogState {
  filters: CatalogFilters
  sort: CatalogSort
  page: number
}

export const EMPTY_FILTERS: CatalogFilters = { stars: [] }

function positiveInt(raw: string | null, min = 1, max = Number.MAX_SAFE_INTEGER): number | undefined {
  if (raw === null || !/^\d{1,9}$/.test(raw)) return undefined
  const value = Number(raw)
  return value >= min && value <= max ? value : undefined
}

function isoDate(raw: string | null): string | undefined {
  if (raw === null || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return undefined
  const [year, month, day] = raw.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  // Rejects 2026-02-30 and the like, which Date would silently roll over.
  return date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? raw : undefined
}

function oneOf<T extends string>(raw: string | null, allowed: readonly T[]): T | undefined {
  return allowed.find((value) => value === raw)
}

export function parseCatalogParams(params: URLSearchParams): CatalogState {
  const q = params.get('q')?.trim().slice(0, Q_MAX_LENGTH)
  const stars = [...new Set(params.getAll('stars').map((s) => positiveInt(s, 1, 5)))]
    .filter((s): s is number => s !== undefined)
    .sort()
  const filters: CatalogFilters = {
    q: q || undefined,
    country_id: positiveInt(params.get('country_id')),
    resort_id: positiveInt(params.get('resort_id')),
    departure_city_id: positiveInt(params.get('departure_city_id')),
    transport_type: oneOf(params.get('transport_type'), TRANSPORT_TYPES),
    date_from: isoDate(params.get('date_from')),
    date_to: isoDate(params.get('date_to')),
    nights_min: positiveInt(params.get('nights_min'), NIGHTS_MIN, NIGHTS_MAX),
    nights_max: positiveInt(params.get('nights_max'), NIGHTS_MIN, NIGHTS_MAX),
    price_min: positiveInt(params.get('price_min'), 0),
    price_max: positiveInt(params.get('price_max'), 0),
    stars,
    // Only "true" is a filter; the UI has no "only sold-out tours" option.
    has_seats: params.get('has_seats') === 'true' ? true : undefined,
  }
  return {
    filters,
    sort: oneOf(params.get('sort'), SORTS) ?? DEFAULT_SORT,
    page: positiveInt(params.get('page')) ?? 1,
  }
}

/** Default values (sort by date, page 1) and empty filters are left out of the URL. */
export function toSearchParams({ filters, sort, page }: CatalogState): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters) as [keyof CatalogFilters, unknown][]) {
    if (key === 'stars') continue
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  for (const star of [...filters.stars].sort()) params.append('stars', String(star))
  if (sort !== DEFAULT_SORT) params.set('sort', sort)
  if (page > 1) params.set('page', String(page))
  return params
}

/** What the catalog sends to GET /api/tours. */
export function toApiParams({ filters, sort, page }: CatalogState): TourSearchParams {
  const params: TourSearchParams = { sort, page, page_size: PAGE_SIZE }
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || (Array.isArray(value) && value.length === 0)) continue
    Object.assign(params, { [key]: value })
  }
  return params
}

/**
 * A filter change always goes back to page 1 (the old page may not exist any more), and a new
 * country clears the resort, which belongs to the old country (form 4.6.2.1, field 4).
 */
export function applyFilterPatch(state: CatalogState, patch: Partial<CatalogFilters>): CatalogState {
  const filters = { ...state.filters, ...patch }
  if ('country_id' in patch && patch.country_id !== state.filters.country_id) {
    filters.resort_id = undefined
  }
  return { ...state, filters, page: 1 }
}

/** Number of active filters, shown on the mobile "Фільтри" button. */
export function countActiveFilters(filters: CatalogFilters): number {
  return Object.entries(filters).filter(([key, value]) => {
    if (key === 'date_to' && filters.date_from !== undefined) return false // one date range
    return Array.isArray(value) ? value.length > 0 : value !== undefined
  }).length
}
