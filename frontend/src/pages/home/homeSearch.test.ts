import { describe, expect, it } from 'vitest'
import { parseCatalogParams, toApiParams } from '../catalog/catalogParams'
import { catalogUrl } from './homeSearch'

const query = (url: string) => new URLSearchParams(url.split('?')[1] ?? '')

describe('catalogUrl', () => {
  it('is the plain catalog when nothing is chosen', () => {
    expect(catalogUrl({})).toBe('/tours')
  })

  it('gives the catalog the same request as its own filters would', () => {
    const url = catalogUrl({ country_id: 2, departure_city_id: 100, date_from: '2099-06-01', date_to: '2099-06-15' })
    expect(url).toBe('/tours?country_id=2&departure_city_id=100&date_from=2099-06-01&date_to=2099-06-15')
    expect(toApiParams(parseCatalogParams(query(url)))).toEqual({
      sort: 'date_asc', page: 1, page_size: 12,
      country_id: 2, departure_city_id: 100, date_from: '2099-06-01', date_to: '2099-06-15',
    })
  })

  it('links a country to the catalog filtered by it', () => {
    expect(catalogUrl({ country_id: 1 })).toBe('/tours?country_id=1')
  })
})
