// Home page -> catalog links (spec 07-home-page.md §2).
//
// The home page never builds a catalog URL by hand: it fills the catalog's own CatalogFilters and
// serialises them with the catalog's toSearchParams(). So a search from the banner opens exactly
// the URL the catalog would have for the same filters, and therefore the same results.
import type { TourSearchParams } from '../../api/types'
import { DEFAULT_SORT, EMPTY_FILTERS, toSearchParams, type CatalogFilters } from '../catalog/catalogParams'

/** What the banner's search form can set: a subset of the catalog's filters. */
export type HomeSearchValues = Pick<CatalogFilters, 'country_id' | 'departure_city_id' | 'date_from' | 'date_to'>

/** `/tours?...` for these filters; `/tours` when none is set. */
export function catalogUrl(values: HomeSearchValues): string {
  const filters: CatalogFilters = { ...EMPTY_FILTERS, ...values }
  const search = toSearchParams({ filters, sort: DEFAULT_SORT, page: 1 }).toString()
  return search ? `/tours?${search}` : '/tours'
}

export const STRIP_SIZE = 4

/** «Гарячі пропозиції»: tours the manager pinned (form 4.6.2.1, field 19), nearest first. */
export const HOT_PARAMS: TourSearchParams = {
  featured: true, has_seats: true, sort: 'date_asc', page: 1, page_size: STRIP_SIZE,
}

/**
 * «Найближчі виїзди». The API already lists only tours for sale (published, a start date from
 * tomorrow, Kyiv). date_asc orders by the first start date, which gives the same order as the
 * card's nearest bookable date: a range that has already begun is bookable from tomorrow, the
 * earliest possible date, so it correctly comes first.
 */
export const NEAREST_PARAMS: TourSearchParams = {
  has_seats: true, sort: 'date_asc', page: 1, page_size: STRIP_SIZE,
}

/** Only the total is needed: it is the same number the catalog shows for this country. */
export function countryCountParams(countryId: number): TourSearchParams {
  return { country_id: countryId, page: 1, page_size: 1 }
}
