import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import {
  applyFilterPatch, parseCatalogParams, type CatalogSort, toSearchParams, type CatalogFilters, type CatalogState,
} from './catalogParams'

/** The catalog's state, read from and written to the URL query string. Every change is a new
 * history entry, so Back returns to the previous search. */
export function useCatalogParams() {
  const [searchParams, setSearchParams] = useSearchParams()
  const state = useMemo(() => parseCatalogParams(searchParams), [searchParams])

  const write = useCallback(
    (next: CatalogState, replace = false) => setSearchParams(toSearchParams(next), { replace }),
    [setSearchParams],
  )

  return {
    state,
    setFilters: (patch: Partial<CatalogFilters>) => write(applyFilterPatch(state, patch)),
    replaceFilters: (filters: CatalogFilters) => write({ ...state, filters, page: 1 }),
    setSort: (sort: CatalogSort) => write({ ...state, sort, page: 1 }),
    setPage: (page: number, replace = false) => write({ ...state, page }, replace),
    reset: () => setSearchParams(new URLSearchParams()),
  }
}
