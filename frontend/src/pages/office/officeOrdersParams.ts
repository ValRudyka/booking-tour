import type { ManagerOrderSort, ManagerOrdersQuery, ManagerQueue, OrderStatus } from '../../api/types'
import type { FilterValues } from '../../components/office/FilterBar'
import { keysOf, MANAGER_QUEUES } from '../../constants/orderLabels'
import { ORDER_STATUS_TONES } from '../../constants/orderStatus'
import {
  readDate, readEnum, readEnumList, readFlag, readPage, readText, writeParams,
} from '../../features/office/urlState'

// The state of «Заявки» in the URL, under the API's own parameter names (like the catalog):
// /office/orders?queue=mine&status=in_progress&created_from=2026-11-01&page=2

export const OFFICE_ORDERS_PAGE_SIZE = 20
export const QUEUES = keysOf(MANAGER_QUEUES)
export const ORDER_STATUSES = Object.keys(ORDER_STATUS_TONES) as OrderStatus[]
const SORTS: readonly ManagerOrderSort[] = ['created_desc', 'created_asc', 'start_asc', 'start_desc']
/** A manager starts from the orders nobody has taken. */
const DEFAULT_QUEUE: ManagerQueue = 'new'
const DEFAULT_SORT: ManagerOrderSort = 'created_desc'

export interface OfficeOrdersFilters {
  number?: string
  client?: string
  status: OrderStatus[]
  created_from?: string
  created_to?: string
  start_from?: string
  start_to?: string
  overdue: boolean
}

export interface OfficeOrdersState {
  queue: ManagerQueue
  sort: ManagerOrderSort
  page: number
  filters: OfficeOrdersFilters
}

export function parseOfficeOrders(params: URLSearchParams): OfficeOrdersState {
  return {
    queue: readEnum(params, 'queue', QUEUES) ?? DEFAULT_QUEUE,
    sort: readEnum(params, 'sort', SORTS) ?? DEFAULT_SORT,
    page: readPage(params),
    filters: {
      number: readText(params, 'number', 30),
      client: readText(params, 'client', 100),
      status: readEnumList(params, 'status', ORDER_STATUSES),
      created_from: readDate(params, 'created_from'),
      created_to: readDate(params, 'created_to'),
      start_from: readDate(params, 'start_from'),
      start_to: readDate(params, 'start_to'),
      overdue: readFlag(params, 'overdue'),
    },
  }
}

export function officeOrdersSearch(state: OfficeOrdersState): URLSearchParams {
  return writeParams({ queue: state.queue, sort: state.sort, page: state.page, ...state.filters },
    { queue: DEFAULT_QUEUE, sort: DEFAULT_SORT, page: 1 })
}

/** GET /manager/orders parameters (repeated `status` keys, see api/client.ts). */
export function officeOrdersQuery(state: OfficeOrdersState): ManagerOrdersQuery {
  const { filters } = state
  return {
    queue: state.queue,
    sort: state.sort,
    page: state.page,
    page_size: OFFICE_ORDERS_PAGE_SIZE,
    ...(filters.number && { number: filters.number }),
    ...(filters.client && { client: filters.client }),
    ...(filters.status.length > 0 && { status: filters.status }),
    ...(filters.created_from && { created_from: filters.created_from }),
    ...(filters.created_to && { created_to: filters.created_to }),
    ...(filters.start_from && { start_from: filters.start_from }),
    ...(filters.start_to && { start_to: filters.start_to }),
    ...(filters.overdue && { overdue: true }),
  }
}

/** The filter bar's values (FilterBar works on URL-shaped values). */
export function filterValuesOf(filters: OfficeOrdersFilters): FilterValues {
  return {
    number: filters.number, client: filters.client, status: filters.status,
    created_from: filters.created_from, created_to: filters.created_to,
    start_from: filters.start_from, start_to: filters.start_to,
    overdue: filters.overdue ? 'true' : undefined,
  }
}

/** Back from the filter bar, validated like a URL. */
export function filtersFromValues(values: FilterValues): OfficeOrdersFilters {
  const params = writeParams(values)
  return parseOfficeOrders(params).filters
}
