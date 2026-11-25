import type { TFunction } from 'i18next'
import type {
  CancelReason, ManagerQueue, NameDisplay, OrderDocumentType, PaymentMethod, PaymentType, StaffAction, UserRole,
} from '../api/types'

// Other fixed value sets of an order, labelled in uk.json (documentType.*, cancelReason.*,
// paymentMethod.*, nameDisplay.*). Like orderStatus.ts, `Record<…>` keeps them complete, and
// orderStatus.test.ts compares them with the enums in src/api/openapi.json.

/** Trip documents the manager uploads (form 4.6.2.2, field 5.1). `cancel_evidence` is the
 * client's own file for a cancellation request: the API never lists it for the client. */
export const DOCUMENT_TYPES: Record<OrderDocumentType, true> = {
  voucher: true, air_ticket: true, insurance_policy: true, info_sheet: true, cancel_evidence: true,
}

/** Довідник «Причини скасувань» (form 4.6.1.3, field 2), in this order in the form. */
export const CANCEL_REASONS: Record<CancelReason, true> = {
  illness: true, change_of_plans: true, data_error: true, visa_refusal: true, other: true,
}

export const PAYMENT_METHODS: Record<PaymentMethod, true> = { card: true, bank_transfer: true }

/** Form 4.6.1.4, field 7. */
export const NAME_DISPLAYS: Record<NameDisplay, true> = { full: true, short: true, anonymous: true }

/** The back office (spec 09). What a manager may do with an order (`staff_actions`, decided by the
 * backend's services/staff_actions.py), in the order the action panel lists them. */
export const STAFF_ACTIONS: Record<StaffAction, true> = {
  take: true, confirm: true, reject: true, documents_ready: true, archive: true, assign: true,
  upload_documents: true, edit_comment: true,
}

/** Tabs of «Заявки» (GET /manager/orders?queue=). */
export const MANAGER_QUEUES: Record<ManagerQueue, true> = { new: true, mine: true, all: true }

export const USER_ROLES: Record<UserRole, true> = { client: true, manager: true, finance: true, admin: true }

export const PAYMENT_TYPES: Record<PaymentType, true> = { payment: true, refund: true }

export function staffActionLabel(t: TFunction, action: StaffAction): string {
  return t(`staffAction.${action}`)
}

export function roleLabel(t: TFunction, role: UserRole): string {
  return t(`userRole.${role}`)
}

export function documentLabel(t: TFunction, type: OrderDocumentType): string {
  return t(`documentType.${type}`)
}

export function cancelReasonLabel(t: TFunction, reason: CancelReason): string {
  return t(`cancelReason.${reason}`)
}

export function paymentMethodLabel(t: TFunction, method: PaymentMethod): string {
  return t(`paymentMethod.${method}`)
}

export function keysOf<T extends string>(record: Record<T, true>): T[] {
  return Object.keys(record) as T[]
}
