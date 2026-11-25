import type { ManagerTourSort, ManagerToursQuery, TourStatus } from '../../../api/types'
import type { FilterValues } from '../../../components/office/FilterBar'
import { TOUR_STATUS_TONES } from '../../../constants/orderStatus'
import { readDate, readEnum, readId, readPage, readText, writeParams } from '../../../features/office/urlState'

// The state of «Тури» in the URL, under the API's own parameter names:
// /office/tours?status=active&country_id=3&departure_from=2027-06-01&sort=title_asc&page=2

export const OFFICE_TOURS_PAGE_SIZE = 20
export const TOUR_STATUSES = Object.keys(TOUR_STATUS_TONES) as TourStatus[]
const SORTS: readonly ManagerTourSort[] = ['updated_desc', 'departure_asc', 'title_asc']
const DEFAULT_SORT: ManagerTourSort = 'updated_desc'

export interface OfficeToursFilters {
  q?: string
  status?: TourStatus
  country_id?: number
  resort_id?: number
  departure_from?: string
  departure_to?: string
}

export interface OfficeToursState {
  sort: ManagerTourSort
  page: number
  filters: OfficeToursFilters
}

export function parseOfficeTours(params: URLSearchParams): OfficeToursState {
  const country = readId(params, 'country_id')
  return {
    sort: readEnum(params, 'sort', SORTS) ?? DEFAULT_SORT,
    page: readPage(params),
    filters: {
      q: readText(params, 'q', 100),
      status: readEnum(params, 'status', TOUR_STATUSES),
      country_id: country,
      // A resort means something only inside its country (the filter bar sets them together).
      resort_id: country !== undefined ? readId(params, 'resort_id') : undefined,
      departure_from: readDate(params, 'departure_from'),
      departure_to: readDate(params, 'departure_to'),
    },
  }
}

export function officeToursSearch(state: OfficeToursState): URLSearchParams {
  return writeParams({ sort: state.sort, page: state.page, ...state.filters },
    { sort: DEFAULT_SORT, page: 1 })
}

/** GET /manager/tours parameters. */
export function officeToursQuery(state: OfficeToursState): ManagerToursQuery {
  const { filters } = state
  return {
    sort: state.sort,
    page: state.page,
    page_size: OFFICE_TOURS_PAGE_SIZE,
    ...(filters.q && { q: filters.q }),
    ...(filters.status && { status: filters.status }),
    ...(filters.country_id !== undefined && { country_id: filters.country_id }),
    ...(filters.resort_id !== undefined && { resort_id: filters.resort_id }),
    ...(filters.departure_from && { departure_from: filters.departure_from }),
    ...(filters.departure_to && { departure_to: filters.departure_to }),
  }
}

/** The filter bar's values (FilterBar works on URL-shaped strings). */
export function filterValuesOf(filters: OfficeToursFilters): FilterValues {
  return {
    q: filters.q, status: filters.status,
    country_id: filters.country_id?.toString(), resort_id: filters.resort_id?.toString(),
    departure_from: filters.departure_from, departure_to: filters.departure_to,
  }
}

/** Back from the filter bar, validated like a URL. */
export function filtersFromValues(values: FilterValues): OfficeToursFilters {
  return parseOfficeTours(writeParams(values)).filters
}
