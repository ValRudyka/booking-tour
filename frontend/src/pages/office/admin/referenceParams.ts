import type { ReferenceKind } from '../../../api/admin'
import type { FilterValues } from '../../../components/office/FilterBar'
import { readEnum, readFlag, readPage, readText, writeParams } from '../../../features/office/urlState'

// /office/references state in the URL (spec 13 §2): the directory tab, the filters and the page.
// The admin lists are not paginated by the API, so filtering and paging happen on the page.

export const REFERENCE_TABS = ['countries', 'resorts', 'cities', 'hotels', 'insurance-types', 'transfer-types'] as const satisfies readonly ReferenceKind[]
export const REFERENCE_PAGE_SIZE = 20

export interface ReferenceState {
  tab: ReferenceKind
  q?: string
  country?: number
  resort?: number
  /** «Показати архівні»: without it only active records are listed. */
  archived: boolean
  page: number
}

const id = (params: URLSearchParams, key: string) => {
  const value = Number(params.get(key))
  return Number.isInteger(value) && value > 0 ? value : undefined
}

/** Which parent filters a directory has. */
export const PARENT_FILTERS: Record<ReferenceKind, { country: boolean; resort: boolean }> = {
  countries: { country: false, resort: false },
  resorts: { country: true, resort: false },
  cities: { country: true, resort: false },
  hotels: { country: true, resort: true },
  'insurance-types': { country: false, resort: false },
  'transfer-types': { country: false, resort: false },
}

export function parseReference(params: URLSearchParams): ReferenceState {
  const tab = readEnum(params, 'tab', REFERENCE_TABS) ?? 'countries'
  const parents = PARENT_FILTERS[tab]
  return {
    tab,
    q: readText(params, 'q', 100),
    country: parents.country ? id(params, 'country') : undefined,
    resort: parents.resort ? id(params, 'resort') : undefined,
    archived: readFlag(params, 'archived'),
    page: readPage(params),
  }
}

export function referenceSearch(state: ReferenceState): URLSearchParams {
  return writeParams({ tab: state.tab, q: state.q, country: state.country, resort: state.resort,
    archived: state.archived, page: state.page }, { tab: 'countries', page: 1 })
}

export function referenceFilterValues(state: ReferenceState): FilterValues {
  return { q: state.q, country: state.country?.toString(), resort: state.resort?.toString(),
    archived: state.archived ? 'true' : undefined }
}

export function referenceFromFilters(state: ReferenceState, values: FilterValues): ReferenceState {
  const params = new URLSearchParams({ tab: state.tab })
  for (const key of ['q', 'country', 'resort', 'archived']) {
    const value = values[key]
    if (typeof value === 'string' && value) params.set(key, value)
  }
  return { ...parseReference(params), page: 1 }
}

/** Case-insensitive search in the given texts. */
export function matches(query: string | undefined, ...texts: (string | null | undefined)[]): boolean {
  if (!query) return true
  const needle = query.toLocaleLowerCase('uk')
  return texts.some((text) => text?.toLocaleLowerCase('uk').includes(needle))
}
