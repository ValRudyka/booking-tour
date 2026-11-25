import { lazy } from 'react'

// The back office loads on demand (router.tsx): the public pages never download its code.
export const OfficeLayout = lazy(() => import('../../layouts/OfficeLayout').then((m) => ({ default: m.OfficeLayout })))
export const OfficeOrdersPage = lazy(() => import('./OfficeOrdersPage').then((m) => ({ default: m.OfficeOrdersPage })))
export const OfficeOrderPage = lazy(() => import('./OfficeOrderPage').then((m) => ({ default: m.OfficeOrderPage })))
export const OfficeToursPage = lazy(() => import('./tours/OfficeToursPage').then((m) => ({ default: m.OfficeToursPage })))
export const TourEditorPage = lazy(() => import('./tours/TourEditorPage').then((m) => ({ default: m.TourEditorPage })))
