import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { City, Country, Hotel, Resort } from './types'

const REFERENCE_STALE_MS = 10 * 60_000 // reference lists change only through the admin

export async function fetchCountries(): Promise<Country[]> {
  return (await api.get<Country[]>('/reference/countries')).data
}

export async function fetchResorts(countryId: number): Promise<Resort[]> {
  return (await api.get<Resort[]>('/reference/resorts', { params: { country_id: countryId } })).data
}

export async function fetchCities(): Promise<City[]> {
  return (await api.get<City[]>('/reference/cities')).data
}

export function useCountries() {
  return useQuery({ queryKey: ['reference', 'countries'], queryFn: fetchCountries,
    staleTime: REFERENCE_STALE_MS })
}

/** Resorts depend on the country (form 4.6.2.1, field 4): nothing is loaded without one. */
export function useResorts(countryId: number | undefined) {
  return useQuery({
    queryKey: ['reference', 'resorts', countryId],
    queryFn: () => fetchResorts(countryId!),
    enabled: countryId !== undefined,
    staleTime: REFERENCE_STALE_MS,
  })
}

export function useCities() {
  return useQuery({ queryKey: ['reference', 'cities'], queryFn: fetchCities,
    staleTime: REFERENCE_STALE_MS })
}

export async function fetchHotels(resortId: number): Promise<Hotel[]> {
  return (await api.get<Hotel[]>('/reference/hotels', { params: { resort_id: resortId } })).data
}

/** Hotels depend on the resort (form 4.6.2.1, field 5): nothing is loaded without one. */
export function useHotels(resortId: number | undefined) {
  return useQuery({
    queryKey: ['reference', 'hotels', resortId],
    queryFn: () => fetchHotels(resortId!),
    enabled: resortId !== undefined,
    staleTime: REFERENCE_STALE_MS,
  })
}
