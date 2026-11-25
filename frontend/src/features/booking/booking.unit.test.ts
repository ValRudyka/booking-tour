import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/client'
import { formatMoney, maskPassport } from '../../utils/format'
import { clearAllDrafts, draftKey, loadDraft, saveDraft, type BookingDraft } from './bookingDraft'
import { isHoldExpired, serverText, touristIssues } from './bookingErrors'
import {
  addMonths, ageOn, isChild, isLatinPassportName, isPassportNumber, passportValidUntil, returnDate,
} from './bookingRules'

const plain = (text: string) => text.replace(/[  ]/g, ' ')

describe('booking rules mirror the backend', () => {
  it('accepts Latin names as in a foreign passport only', () => {
    expect(isLatinPassportName('Shevchenko')).toBe(true)
    expect(isLatinPassportName("O'Neil-Smith  Jr")).toBe(true)   // spaces collapsed like the backend
    expect(isLatinPassportName('Шевченко')).toBe(false)
    expect(isLatinPassportName('-Taras')).toBe(false)             // must start with a letter
    expect(isLatinPassportName('Taras2')).toBe(false)
    expect(isLatinPassportName('A'.repeat(101))).toBe(false)
  })

  it('checks passport numbers after removing spaces and upper-casing', () => {
    expect(isPassportNumber('fx 123456')).toBe(true)
    expect(isPassportNumber('FX-1234')).toBe(false)
    expect(isPassportNumber('FX1')).toBe(false)
    expect(isPassportNumber('A'.repeat(21))).toBe(false)
  })

  it('adds months like add_months (end of month clamp)', () => {
    expect(addMonths('2099-08-31', 6)).toBe('2100-02-28')
    expect(addMonths('2028-08-31', 6)).toBe('2029-02-28')
    expect(addMonths('2027-08-31', 6)).toBe('2028-02-29')       // leap year
    expect(addMonths('2099-06-17', 6)).toBe('2099-12-17')
    expect(passportValidUntil(returnDate('2099-06-10', 7))).toBe('2099-12-17')
  })

  it('a child is under 12 on the start date', () => {
    expect(isChild('2087-06-10', '2099-06-10')).toBe(false)     // the 12th birthday that day
    expect(isChild('2087-06-11', '2099-06-10')).toBe(true)
    expect(ageOn('2096-02-29', '2099-02-28')).toBe(2)           // 29 Feb birthday not reached yet
  })
})

describe('booking draft', () => {
  const draft: BookingDraft = {
    step: 1, date: '2099-06-10', adults: 1, children: 0, orderId: 1, insurance_type_id: null,
    transfer_type_id: null, promo: '', wishes: '',
    tourists: [{ last_name_lat: 'KOVALENKO', first_name_lat: 'OLENA', birth_date: '1990-05-14', passport_expiry: null }],
  }

  it('never stores a passport number, even if one is passed in', () => {
    const withNumber = { ...draft, tourists: [{ ...draft.tourists[0], passport_number: 'FX123456' }] }
    saveDraft(501, 7, withNumber as BookingDraft)
    expect(window.sessionStorage.getItem(draftKey(501, 7))).not.toContain('FX123456')
    expect(loadDraft(501, 7)).toEqual(draft)
  })

  it('ignores a damaged draft and keeps drafts apart by user', () => {
    window.sessionStorage.setItem(draftKey(501, 7), '{"step": "x"}')
    expect(loadDraft(501, 7)).toBeNull()
    saveDraft(501, 7, draft)
    expect(loadDraft(502, 7)).toBeNull()
    clearAllDrafts()
    expect(loadDraft(501, 7)).toBeNull()
  })
})

describe('booking errors', () => {
  it('reads tourist field errors and the backend texts', () => {
    const error = new ApiError('validation', 422, 'x', null, [
      { loc: ['body', 'tourists', 1, 'passport_number'], msg: 'Серія та номер…', type: 'checkout_rule' },
      { loc: ['body', 'tourists', 0, 'birth_date'], msg: 'Input should be a valid date', type: 'date_from_datetime_parsing' },
    ])
    expect(touristIssues(error)).toEqual([
      { index: 1, field: 'passport_number', message: 'Серія та номер…' },
      { index: 0, field: 'birth_date', message: 'Перевірте значення цього поля' },   // never pydantic's English
    ])
    const expired = new ApiError('client', 409, 'm', 'Час на оформлення замовлення минув — замовлення скасовано')
    expect(isHoldExpired(expired)).toBe(true)
    expect(serverText(new ApiError('validation', 422, 'generic', 'Промокод не знайдено'))).toBe('Промокод не знайдено')
  })
})

describe('checkout formatting', () => {
  it('shows exact amounts with kopecks and masks passports', () => {
    expect(plain(formatMoney('63872.76'))).toBe('63 872,76')
    expect(plain(formatMoney('0.00'))).toBe('0,00')
    expect(maskPassport('FX123456')).toBe('FX****56')
    expect(maskPassport('AB12')).toBe('****')
  })
})
