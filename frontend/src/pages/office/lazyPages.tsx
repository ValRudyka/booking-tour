import { lazy } from 'react'

// The back office loads on demand (router.tsx): the public pages never download its code.
export const OfficeLayout = lazy(() => import('../../layouts/OfficeLayout').then((m) => ({ default: m.OfficeLayout })))
export const OfficeOrdersPage = lazy(() => import('./OfficeOrdersPage').then((m) => ({ default: m.OfficeOrdersPage })))
