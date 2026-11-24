import { describe, expect, it } from 'vitest'
import {
  applyFilterPatch, countActiveFilters, parseCatalogParams, toApiParams, toSearchParams,
} from './catalogParams'

const parse = (query: string) => parseCatalogParams(new URLSearchParams(query))

describe('parseCatalogParams', () => {
  it('reads every filter, the sort and the page', () => {
    const state = parse('q=Coral&country_id=1&resort_id=10&departure_city_id=100&transport_type=air'
      + '&date_from=2026-12-01&date_to=2026-12-31&nights_min=7&nights_max=10&price_min=20000'
      + '&price_max=50000&stars=5&stars=4&has_seats=true&sort=price_asc&page=2')
    expect(state).toEqual({
      filters: {
        q: 'Coral', country_id: 1, resort_id: 10, departure_city_id: 100, transport_type: 'air',
        date_from: '2026-12-01', date_to: '2026-12-31', nights_min: 7, nights_max: 10,
        price_min: 20000, price_max: 50000, stars: [4, 5], has_seats: true,
      },
      sort: 'price_asc',
      page: 2,
    })
  })

  it('drops values the API would reject instead of sending them', () => {
    const state = parse('country_id=abc&nights_min=0&nights_max=31&date_from=2026-02-30'
      + '&stars=9&stars=4&stars=4&transport_type=ship&sort=name&page=-1&price_min=1.5&has_seats=false')
    expect(state.filters).toEqual({
      q: undefined, country_id: undefined, resort_id: undefined, departure_city_id: undefined,
      transport_type: undefined, date_from: undefined, date_to: undefined, nights_min: undefined,
      nights_max: undefined, price_min: undefined, price_max: undefined, stars: [4], has_seats: undefined,
    })
    expect(state.sort).toBe('date_asc')
    expect(state.page).toBe(1)
  })

  it('trims the search text and caps it at the API limit', () => {
    expect(parse('q=%20%20').filters.q).toBeUndefined()
    expect(parse(`q=${'a'.repeat(150)}`).filters.q).toHaveLength(100)
  })
})

describe('toSearchParams', () => {
  it('leaves defaults and empty filters out of the URL and repeats stars', () => {
    const params = toSearchParams({ filters: { stars: [5, 4], country_id: 1, q: undefined }, sort: 'date_asc', page: 1 })
    expect(params.toString()).toBe('country_id=1&stars=4&stars=5')
  })

  it('round-trips through the parser', () => {
    const query = 'country_id=2&nights_min=3&stars=3&sort=rating_desc&page=4'
    expect(toSearchParams(parse(query)).toString()).toBe(query)
  })
})

describe('toApiParams', () => {
  it('maps the state to GET /api/tours parameters with 12 per page', () => {
    expect(toApiParams(parse('country_id=1&stars=4&stars=5&page=3&sort=price_desc'))).toEqual({
      country_id: 1, stars: [4, 5], page: 3, page_size: 12, sort: 'price_desc',
    })
  })

  it('sends no empty star list', () => {
    expect(toApiParams(parse(''))).toEqual({ sort: 'date_asc', page: 1, page_size: 12 })
  })
})

describe('applyFilterPatch', () => {
  it('goes back to page 1 on any filter change', () => {
    expect(applyFilterPatch(parse('page=5&stars=4'), { stars: [4, 5] }).page).toBe(1)
  })

  it('clears the resort when the country changes', () => {
    const next = applyFilterPatch(parse('country_id=1&resort_id=10'), { country_id: 2 })
    expect(next.filters).toMatchObject({ country_id: 2, resort_id: undefined })
  })

  it('keeps the resort when another filter changes', () => {
    const next = applyFilterPatch(parse('country_id=1&resort_id=10'), { nights_min: 7 })
    expect(next.filters).toMatchObject({ country_id: 1, resort_id: 10 })
  })
})

describe('countActiveFilters', () => {
  it('counts a date range once', () => {
    expect(countActiveFilters(parse('date_from=2026-12-01&date_to=2026-12-31&stars=4').filters)).toBe(2)
  })
})
