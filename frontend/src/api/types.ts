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
