import { describe, expect, it } from 'vitest'
import uk from '../i18n/uk.json'
import {
  CANCEL_REASONS, DOCUMENT_TYPES, MANAGER_QUEUES, NAME_DISPLAYS, PAYMENT_METHODS, PAYMENT_TYPES, STAFF_ACTIONS, TOUR_ACTIONS,
  USER_ROLES,
} from './orderLabels'
import { STATUS_SECTIONS, STATUS_TONES } from './orderStatus'

// The enums exactly as the backend publishes them (`npm run gen:api` saves this snapshot). When
// the backend gets a new status, regenerating the API makes this test fail until the status has
// a tone and a Ukrainian label.
// Loaded through Vite's glob import, so TypeScript does not infer a type for the whole schema.
const openapi = Object.values(import.meta.glob('../api/openapi.json', { eager: true, import: 'default' }))[0] as {
  components: { schemas: Record<string, { enum?: string[] }> }
}

function backendEnum(name: string): string[] {
  const values = openapi.components.schemas[name]?.enum
  if (!values) throw new Error(`${name} is not an enum in src/api/openapi.json`)
  return [...values].sort()
}

const texts = uk as unknown as Record<string, Record<string, string>>

describe('status dictionary (src/constants/orderStatus.ts)', () => {
  it.each([
    ['OrderStatus', 'order'],
    ['PaymentStatus', 'payment'],
    ['ReviewStatus', 'review'],
    ['TransactionStatus', 'transaction'],
    ['TourStatus', 'tour'],
  ] as const)('%s: every backend value has a tone and a Ukrainian label, and nothing extra', (schema, kind) => {
    const values = backendEnum(schema)
    expect(Object.keys(STATUS_TONES[kind]).sort()).toEqual(values)
    const labels = texts[STATUS_SECTIONS[kind]]
    expect(Object.keys(labels).sort()).toEqual(values)
    for (const value of values) expect(labels[value].trim()).not.toBe('')
  })

  it.each([
    ['OrderDocumentType', DOCUMENT_TYPES, 'documentType'],
    ['CancelReason', CANCEL_REASONS, 'cancelReason'],
    ['PaymentMethod', PAYMENT_METHODS, 'paymentMethod'],
    ['NameDisplay', NAME_DISPLAYS, 'nameDisplay'],
    ['StaffAction', STAFF_ACTIONS, 'staffAction'],
    ['ManagerQueue', MANAGER_QUEUES, 'managerQueue'],
    ['UserRole', USER_ROLES, 'userRole'],
    ['PaymentType', PAYMENT_TYPES, 'paymentType'],
    ['TourAction', TOUR_ACTIONS, 'tourAction'],
  ] as const)('%s: every backend value has a label', (schema, record, section) => {
    const values = backendEnum(schema)
    expect(Object.keys(record).sort()).toEqual(values)
    expect(Object.keys(texts[section]).sort()).toEqual(values)
  })

  it('client actions in the snapshot are the ones the cabinet knows', () => {
    expect(backendEnum('ClientAction')).toEqual(['cancel', 'cancel_request', 'continue_checkout',
      'download_documents', 'pay', 'review', 'view_review'])
  })
})
