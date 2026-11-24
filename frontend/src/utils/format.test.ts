import { describe, expect, it } from 'vitest'
import { formatDate, formatPrice, formatRating, kyivToday, nearestDeparture } from './format'

// Intl uses a narrow no-break space as the uk-UA thousands separator.
const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ')

describe('formatPrice', () => {
  it('groups thousands', () => {
    expect(plain(formatPrice('32000.00'))).toBe('32 000')
    expect(plain(formatPrice('1234567.00'))).toBe('1 234 567')
  })

  it('rounds kopecks half up without float errors', () => {
    expect(plain(formatPrice('32000.50'))).toBe('32 001')
    expect(plain(formatPrice('32000.49'))).toBe('32 000')
    // Too large for a float to hold exactly; as a decimal string it still rounds like the backend.
    expect(plain(formatPrice('10000000000000000.50'))).toBe('10 000 000 000 000 001')
  })
})

describe('formatRating', () => {
  it('uses a decimal comma and one digit', () => {
    expect(formatRating('4.60')).toBe('4,6')
    expect(formatRating('5.00')).toBe('5,0')
  })
})

describe('formatDate', () => {
  it('formats an ISO date as DD.MM.YYYY', () => {
    expect(formatDate('2026-12-01')).toBe('01.12.2026')
  })
})

describe('kyivToday', () => {
  it('uses the Kyiv date, not the visitor\'s', () => {
    // 22:30 UTC on 31 Dec is already 1 Jan in Kyiv (UTC+2 in winter).
    expect(kyivToday(new Date('2026-12-31T22:30:00Z'))).toBe('2027-01-01')
    expect(kyivToday(new Date('2026-12-31T21:30:00Z'))).toBe('2026-12-31')
  })
})

describe('nearestDeparture', () => {
  const today = '2026-12-10'

  it('is the first start date when it is still ahead', () => {
    expect(nearestDeparture('2026-12-20', '2026-12-31', today)).toBe('2026-12-20')
  })

  it('is today once the range of start dates has begun', () => {
    expect(nearestDeparture('2026-12-01', '2026-12-31', today)).toBe(today)
  })

  it('is the single date of a one-day range', () => {
    expect(nearestDeparture('2026-12-15', '2026-12-15', today)).toBe('2026-12-15')
  })
})
