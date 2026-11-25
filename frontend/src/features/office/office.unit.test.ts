import { describe, expect, it } from 'vitest'
import {
  filtersFromValues, officeOrdersQuery, officeOrdersSearch, parseOfficeOrders,
} from '../../pages/office/officeOrdersParams'
import { officeHome, officeMenu, officeOrderPath } from './menu'
import { deadlineAllowed, normalizePnr, PNR_PATTERN } from './orderRules'
import { readDate, readEnumList, readPage, writeParams } from './urlState'

describe('office URL state', () => {
  it('keeps only real dates, known values and sane pages', () => {
    const params = new URLSearchParams('a=2099-02-28&b=2099-02-30&c=28.02.2099&s=paid&s=x&s=paid&page=-3')
    expect(readDate(params, 'a')).toBe('2099-02-28')
    expect(readDate(params, 'b')).toBeUndefined()
    expect(readDate(params, 'c')).toBeUndefined()
    expect(readEnumList(params, 's', ['paid', 'archived'])).toEqual(['paid'])
    expect(readPage(params)).toBe(1)
  })

  it('writes lists as repeated keys and leaves out empty values and defaults', () => {
    expect(writeParams({ q: 'new', page: 1, status: ['paid', 'in_progress'], client: '', overdue: false, x: undefined },
      { q: 'new', page: 1 }).toString()).toBe('status=paid&status=in_progress')
  })

  it('round-trips the orders state through the URL', () => {
    const state = parseOfficeOrders(new URLSearchParams('queue=all&status=paid&client=Олена&overdue=true&page=3'))
    expect(parseOfficeOrders(officeOrdersSearch(state))).toEqual(state)
    expect(officeOrdersQuery(state)).toEqual({
      queue: 'all', sort: 'created_desc', page: 3, page_size: 20, client: 'Олена', status: ['paid'], overdue: true,
    })
    expect(parseOfficeOrders(new URLSearchParams('queue=bogus')).queue).toBe('new')
  })

  it('validates what comes back from the filter bar like a URL', () => {
    expect(filtersFromValues({ status: ['paid', 'nope'], created_from: '2099-13-01', overdue: 'true' })).toEqual({
      number: undefined, client: undefined, status: ['paid'], created_from: undefined, created_to: undefined,
      start_from: undefined, start_to: undefined, overdue: true,
    })
  })
})

describe('order rules (mirror services/order_processing.py)', () => {
  it('accepts a PNR of 5–20 Latin letters and digits after upper-casing', () => {
    expect(PNR_PATTERN.test(normalizePnr(' abc12 '))).toBe(true)
    expect(PNR_PATTERN.test('AB-12')).toBe(false)
    expect(PNR_PATTERN.test('A'.repeat(21))).toBe(false)
  })

  it('allows the operator deadline from today to the start date', () => {
    expect(deadlineAllowed('2099-01-01', '2099-01-01', '2099-01-10')).toBe(true)
    expect(deadlineAllowed('2099-01-10', '2099-01-01', '2099-01-10')).toBe(true)
    expect(deadlineAllowed('2098-12-31', '2099-01-01', '2099-01-10')).toBe(false)
    expect(deadlineAllowed('2099-01-11', '2099-01-01', '2099-01-10')).toBe(false)
  })
})

describe('office menu', () => {
  it('has no sections for a client and a home for every staff role', () => {
    expect(officeMenu('client')).toEqual([])
    expect(officeHome('client')).toBeNull()
    expect([officeHome('manager'), officeHome('finance'), officeHome('admin')])
      .toEqual(['/office/orders', '/office/transactions', '/office/users'])
  })

  it('leads notifications to an order page only where one exists', () => {
    expect(officeOrderPath('manager', 5)).toBe('/office/orders/5')
    expect(officeOrderPath('finance', 5)).toBeNull()
  })
})
