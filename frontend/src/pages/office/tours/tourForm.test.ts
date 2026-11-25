import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import { isPositiveMoney, MONEY_PATTERN, normalizeFlight, FLIGHT_PATTERN } from '../../../features/office/tourRules'
import { makeManagerTour } from '../../../test/officeFixtures'
import { formFieldOf, payloadOf, sameTour, stepOfField, valuesOf } from './tourForm'
import { filtersFromValues, officeToursQuery, parseOfficeTours } from './officeToursParams'

describe('tour form mapping (spec 10)', () => {
  it('sends the saved tour back unchanged, prices as strings', () => {
    const tour = makeManagerTour()
    const body = payloadOf(valuesOf(tour))
    expect(body).toMatchObject({
      title_uk: 'Coral Bay, Хургада', title_en: 'Coral Bay, Hurghada', hotel_id: 300, transport_type: 'air',
      departure_city_id: 100, flight_out: 'PQ 7121', flight_back: null, departure_from: '2099-06-01',
      departure_to: '2099-06-20', nights: 7, seats_total: 20, base_price: '850.00', child_price: null, currency: 'EUR',
      meal_plan: 'ai', included: ['Авіапереліт'], excluded: [],
      program_days: [{ day_number: 1, description: 'Приліт' }, { day_number: 2, description: 'Пляж' }],
    })
    expect(typeof body.base_price).toBe('string')
    expect(sameTour(valuesOf(tour), valuesOf(tour))).toBe(true)
  })

  it('numbers program days by position: removing or moving a day renumbers them', () => {
    const values = valuesOf(makeManagerTour())
    values.program_days = [{ description: 'Пляж' }, { description: 'Приліт' }, { description: 'Виліт' }]
    expect(payloadOf(values).program_days).toEqual([
      { day_number: 1, description: 'Пляж' }, { day_number: 2, description: 'Приліт' }, { day_number: 3, description: 'Виліт' }])
    values.program_days.splice(0, 1)
    expect(payloadOf(values).program_days?.map((d) => d.day_number)).toEqual([1, 2])
  })

  it('sends flights only for air, no departure city without transport, empty title as null', () => {
    const values = { ...valuesOf(makeManagerTour()), title_uk: '  ', flight_back: 'pq  7122' }
    expect(payloadOf(values)).toMatchObject({ title_uk: null, flight_back: 'PQ 7122' })
    expect(payloadOf({ ...values, transport_type: 'bus' })).toMatchObject({ flight_out: null, flight_back: null, departure_city_id: 100 })
    expect(payloadOf({ ...values, transport_type: 'none' })).toMatchObject({ departure_city_id: null })
  })

  it('keeps money exact: comma decimals and no floats', () => {
    const values = { ...valuesOf(makeManagerTour()), base_price: '1234567890,99', child_price: '' }
    expect(payloadOf(values)).toMatchObject({ base_price: '1234567890.99', child_price: null })
    expect(isPositiveMoney('0.00')).toBe(false)
    expect(isPositiveMoney('0,01')).toBe(true)
    expect(MONEY_PATTERN.test('850.505')).toBe(false)
    expect(MONEY_PATTERN.test('850,5')).toBe(true)
  })

  it('maps server fields to form fields and steps', () => {
    expect(stepOfField('departure_to')).toBe('dates')
    expect(formFieldOf('departure_from')).toBe('dates')
    expect(stepOfField('hotel_id')).toBe('basics')
    expect(stepOfField('program_days')).toBe('program')
    expect(stepOfField('seats_total')).toBe('dates')
  })

  it('treats a changed date range as a change', () => {
    const saved = valuesOf(makeManagerTour())
    expect(sameTour(saved, { ...saved, dates: [dayjs('2099-06-01'), dayjs('2099-06-21')] })).toBe(false)
  })

  it('checks flight numbers like the backend', () => {
    expect(FLIGHT_PATTERN.test(normalizeFlight(' qu   4433 '))).toBe(true)
    expect(FLIGHT_PATTERN.test(normalizeFlight('рейс 1'))).toBe(false)
  })
})

describe('tour list URL state', () => {
  it('reads valid values, drops a resort without its country and builds the API query', () => {
    const state = parseOfficeTours(new URLSearchParams('status=active&status_x=1&country_id=2&resort_id=20&departure_from=2099-06-01&departure_to=2099-02-30&sort=title_asc&page=3'))
    expect(officeToursQuery(state)).toEqual({
      sort: 'title_asc', page: 3, page_size: 20, status: 'active', country_id: 2, resort_id: 20, departure_from: '2099-06-01',
    })
    expect(parseOfficeTours(new URLSearchParams('resort_id=20&status=bogus')).filters).toEqual({
      q: undefined, status: undefined, country_id: undefined, resort_id: undefined, departure_from: undefined, departure_to: undefined,
    })
    expect(filtersFromValues({ q: ' Хург ', country_id: 'x' })).toMatchObject({ q: 'Хург', country_id: undefined })
  })
})
