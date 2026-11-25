// Short names for the generated API types (src/api/schema.d.ts, `npm run gen:api`).
// Never hand-write API types: regenerate after every backend schema change.
import type { components, operations } from './schema'

type Schemas = components['schemas']

export type TourCard = Schemas['TourCardOut']
export type TourPage = Schemas['Page_TourCardOut_']
export type Country = Schemas['CountryOut']
export type Resort = Schemas['ResortOut']
export type City = Schemas['CityOut']
export type TransportType = Schemas['TransportType']
export type MealPlan = Schemas['MealPlan']

/** Query parameters of GET /api/tours, exactly as the backend declares them. */
export type TourSearchParams = NonNullable<operations['search_tours_api_tours_get']['parameters']['query']>
export type TourSort = NonNullable<TourSearchParams['sort']>
export type TourDetail = Schemas['TourDetailOut']
export type HotelDetail = Schemas['HotelDetailOut']
export type PublicReview = Schemas['PublicReviewOut']
export type ReviewPage = Schemas['Page_PublicReviewOut_']
export type User = Schemas['UserOut']
export type UserRole = Schemas['UserRole']
export type TokenOut = Schemas['TokenOut']
export type RegisterRequest = Schemas['RegisterRequest']
export type SiteContacts = Schemas['SiteContactsOut']

// Checkout (ТЗ 4.5.3, form 4.6.1.2)
export type Price = Schemas['PriceOut']
export type OrderStatus = Schemas['OrderStatus']
export type OrderSummary = Schemas['OrderOut']
export type OrderWithPrice = Schemas['OrderWithPriceOut']
/** GET /orders/{id}: price is null when it cannot be rebuilt exactly after confirm. */
export type OrderDetailWithPrice = Schemas['OrderDetailPriceOut']
export type OrderSummaryPage = Schemas['Page_OrderOut_']
export type Tourist = Schemas['TouristOut']
export type TouristIn = Schemas['TouristIn']
export type QuoteRequest = Schemas['QuoteRequest']
export type OrderCreate = Schemas['OrderCreate']
export type OrderUpdate = Schemas['OrderUpdate']
export type ServiceOption = Schemas['ServiceOptionOut']
export type SavedPassport = Schemas['PassportOut']
