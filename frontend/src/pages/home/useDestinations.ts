import { useQueries } from '@tanstack/react-query'
import { fetchTours } from '../../api/catalog'
import { useCountries } from '../../api/reference'
import type { Country } from '../../api/types'
import { countryCountParams } from './homeSearch'

export interface Destination {
  country: Country
  /** The same number the catalog shows for this country. */
  tours: number
}

const byName = new Intl.Collator('uk')

/**
 * «Популярні напрямки»: the countries from the reference list with the number of tours for sale.
 * The API has no count per country, so this asks the catalog once per country with page_size=1
 * and reads `total` (13 small requests with the current reference data). Backlog: a
 * GET /reference/countries?with_tours=true with tours_count would replace them with one request.
 * Countries with no tours (e.g. the departure countries) are left out; the most tours come first.
 */
export function useDestinations() {
  const countries = useCountries()
  const counts = useQueries({
    queries: (countries.data ?? []).map((country) => {
      const params = countryCountParams(country.id)
      return { queryKey: ['tours', params], queryFn: () => fetchTours(params) }
    }),
  })

  const failed = counts.find((query) => query.isError)
  const error = countries.error ?? failed?.error ?? null
  const isPending = countries.isPending || counts.some((query) => query.isPending)

  const destinations: Destination[] = isPending || error ? [] : (countries.data ?? [])
    .map((country, index) => ({ country, tours: counts[index].data?.total ?? 0 }))
    .filter((destination) => destination.tours > 0)
    .sort((a, b) => b.tours - a.tours || byName.compare(a.country.name_uk, b.country.name_uk))

  const retry = () => {
    if (countries.isError) void countries.refetch()
    for (const query of counts) if (query.isError) void query.refetch()
  }

  return { destinations, isPending: isPending && !error, error, retry }
}
