// Short names for the generated API types (src/api/schema.d.ts, `npm run gen:api`).
// Never hand-write API types: regenerate after every backend schema change.
import type { components, operations } from './schema'

type Schemas = components['schemas']

export type TourCard = Schemas['TourCardOut']
export type FavoriteTour = Schemas['FavoriteOut']
export type FavoritePage = Schemas['Page_FavoriteOut_']
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
export type ProfileUpdate = Schemas['ProfileUpdate']
export type PasswordChange = Schemas['PasswordChange']
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
export type SavedPassportIn = Schemas['PassportIn']

// Payment (ТЗ 4.5.3 steps 7.2–9, spec 05)
export type PaymentMethod = Schemas['PaymentMethod']
export type PayOut = Schemas['PayOut']
export type BankDetails = Schemas['BankDetailsOut']
export type PaymentShort = Schemas['PaymentShortOut']

// Client cabinet (spec 06)
export type OrderGroup = Schemas['OrderGroup']
export type ClientAction = Schemas['ClientAction']
/** POST /cancel and /cancel-request answer the order without the price. */
export type OrderDetail = Schemas['OrderDetailOut']
export type PaymentStatus = Schemas['PaymentStatus']
export type TransactionStatus = Schemas['TransactionStatus']
export type OrderDocumentType = Schemas['OrderDocumentType']
export type OrderDocument = Schemas['DocumentOut']
export type CancelReason = Schemas['CancelReason']
export type UploadLimits = Schemas['UploadLimitsOut']
export type CancelRequestForm = Schemas['CancelRequestFormOut']
export type StatusHistory = Schemas['StatusHistoryOut']
export type ReviewStatus = Schemas['ReviewStatus']
export type NameDisplay = Schemas['NameDisplay']
export type MyReview = Schemas['MyReviewOut']
export type OrderReview = Schemas['OrderReviewOut']
export type AppNotification = Schemas['NotificationOut']
export type NotificationPage = Schemas['NotificationPage']

// Back office (spec 09): the manager's order queue and order card
export type StaffAction = Schemas['StaffAction']
export type StaffActionInfo = Schemas['StaffActionOut']
export type ManagerQueue = Schemas['ManagerQueue']
export type ManagerOrderSort = Schemas['ManagerOrderSort']
export type ManagerOrderRow = Schemas['ManagerOrderOut']
export type ManagerOrderPage = Schemas['ManagerOrderPage']
export type ManagerOrder = Schemas['ManagerOrderDetailOut']
export type StaffOrderDocument = Schemas['StaffOrderDocumentOut']
/** POST /manager/orders/{id}/documents answers the new rows (without can_delete). */
export type StaffUploadedDocument = Schemas['StaffDocumentOut']
export type StaffHistory = Schemas['StaffHistoryOut']
export type StaffPayment = Schemas['StaffPaymentOut']
export type ManagerShort = Schemas['ManagerShortOut']
export type DocumentRules = Schemas['DocumentRulesOut']
export type PaymentType = Schemas['PaymentType']
/** Query parameters of GET /api/manager/orders, exactly as the backend declares them. */
export type ManagerOrdersQuery = NonNullable<operations['list_orders_api_manager_orders_get']['parameters']['query']>

// Back office (spec 10): the manager's tours
export type TourStatus = Schemas['TourStatus']
export type Currency = Schemas['Currency']
export type Hotel = Schemas['HotelOut']
export type TourAction = Schemas['TourAction']
export type TourActionInfo = Schemas['TourActionOut']
export type LockedField = Schemas['LockedFieldOut']
export type ManagerTourSort = Schemas['ManagerTourSort']
export type ManagerTourRow = Schemas['ManagerTourListItem']
export type ManagerTourPage = Schemas['Page_ManagerTourListItem_']
export type ManagerTour = Schemas['ManagerTourOut']
export type ManagerTourHotel = Schemas['ManagerTourHotelOut']
export type TourImage = Schemas['TourImageOut']
export type TourCreate = Schemas['TourCreate']
export type TourUpdate = Schemas['TourUpdate']
export type TourCopyIn = Schemas['TourCopyIn']
export type TourRules = Schemas['TourRulesOut']
/** Query parameters of GET /api/manager/tours, exactly as the backend declares them. */
export type ManagerToursQuery = NonNullable<operations['list_tours_api_manager_tours_get']['parameters']['query']>
