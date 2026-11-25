// Client-side checks of the reference data forms (spec 13 §2). They only help: the backend checks
// the same again and its text is shown in the dialog. Keep them in step with
// backend/app/services/reference_admin.py (_clean, _hotel_facts) and services/text_lists.py.

export const NAME_MAX = 100              // name_uk / name_en of countries, cities, resorts, services
export const HOTEL_NAME_MAX = 150
export const DESCRIPTION_MAX = 5000
export const ISO_RE = /^[A-Za-z]{2}$/    // ISO 3166-1 alpha-2, upper-cased by the server
export const IATA_RE = /^[A-Za-z]{3}$/
export const STARS = [1, 2, 3, 4, 5] as const
export const BEACH_LINES = [1, 2, 3, 4, 5] as const
export const MAX_DISTANCE_TO_BEACH_M = 50_000
export const MAX_DISTANCE_TO_AIRPORT_KM = 1_000
export const MAX_PRICE_UAH = 1_000_000
/** services/text_lists.py: at most 20 items of 200 characters (amenities, room types). */
export const LIST_MAX_ITEMS = 20
export const LIST_ITEM_MAX = 200
