// Reading and writing back-office list state in the URL (spec 09 §1: filters and the page live in
// the URL). Every value read from the address bar is validated: anything malformed is dropped,
// so a hand-edited link never reaches the API as a 422. Each list has its own params file built
// from these helpers (e.g. pages/office/officeOrdersParams.ts).

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function readText(params: URLSearchParams, key: string, maxLength = 100): string | undefined {
  const value = params.get(key)?.trim()
  return value ? value.slice(0, maxLength) : undefined
}

/** A YYYY-MM-DD date that really exists (2026-02-30 is dropped). */
export function readDate(params: URLSearchParams, key: string): string | undefined {
  const value = params.get(key)
  if (!value || !ISO_DATE.test(value)) return undefined
  const date = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value) ? value : undefined
}

export function readEnum<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[]): T | undefined {
  const value = params.get(key)
  return value !== null && (allowed as readonly string[]).includes(value) ? value as T : undefined
}

/** Repeated keys (status=paid&status=in_progress), known values only, without duplicates. */
export function readEnumList<T extends string>(params: URLSearchParams, key: string, allowed: readonly T[]): T[] {
  return [...new Set(params.getAll(key))].filter((v): v is T => (allowed as readonly string[]).includes(v))
}

export function readPage(params: URLSearchParams, key = 'page'): number {
  const value = Number(params.get(key))
  return Number.isInteger(value) && value >= 1 && value <= 10_000 ? value : 1
}

export function readFlag(params: URLSearchParams, key: string): boolean {
  return params.get(key) === 'true'
}

export type UrlValue = string | number | boolean | readonly string[] | null | undefined

/** URLSearchParams from a flat object: empty values, `false` and the given defaults are left out,
 * lists become repeated keys. */
export function writeParams(values: Record<string, UrlValue>, defaults: Record<string, UrlValue> = {}): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === '' || value === false) continue
    if (defaults[key] === value) continue
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item)
    } else {
      params.set(key, String(value))
    }
  }
  return params
}
