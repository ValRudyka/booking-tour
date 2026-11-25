import { Skeleton } from 'antd'
import { Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router'
import { AuthRoot } from './features/auth/AuthProvider'
import { RequireAuth } from './features/auth/RequireAuth'
import { STAFF_ROLES } from './features/auth/redirect'
import { CabinetLayout } from './layouts/CabinetLayout'
import { PublicLayout } from './layouts/PublicLayout'
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { BookingPage } from './pages/booking/BookingPage'
import { OrderDetailsPage } from './pages/cabinet/OrderDetailsPage'
import { FavoritesPage } from './pages/cabinet/FavoritesPage'
import { OrdersPage } from './pages/cabinet/OrdersPage'
import { ProfilePage } from './pages/cabinet/ProfilePage'
import { TouristsPage } from './pages/cabinet/TouristsPage'
import { ReviewPage } from './pages/cabinet/ReviewPage'
import { CatalogPage } from './pages/catalog/CatalogPage'
import { HomePage } from './pages/home/HomePage'
import { AboutPage } from './pages/info/AboutPage'
import { ContactsPage } from './pages/info/ContactsPage'
import { FaqPage } from './pages/info/FaqPage'
import { PrivacyPage, TermsPage } from './pages/info/LegalPages'
import { NotFoundPage } from './pages/NotFoundPage'
import { COMING_SOON } from './features/office/menu'
import { OfficeLayout, OfficeOrderPage, OfficeOrdersPage } from './pages/office/lazyPages'
import { OfficeComingSoon, OfficeHome, RequireOfficeRole } from './pages/office/OfficeHome'
import { PayPage } from './pages/payment/PayPage'
import { PaymentCancelPage, PaymentSuccessPage } from './pages/payment/PaymentResultPages'
import { RouteErrorPage } from './pages/RouteErrorPage'
import { TourDetailsPage } from './pages/tour/TourDetailsPage'

const loading = <Skeleton active={false} paragraph={{ rows: 6 }} />
const suspended = (node: ReactNode) => <Suspense fallback={loading}>{node}</Suspense>

export const routes: RouteObject[] = [
  {
    // AuthProvider wraps every page (it needs the router to send a user to /login).
    element: <AuthRoot />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <PublicLayout />,
        children: [
          { index: true, element: <HomePage /> },
          { path: 'tours', element: <CatalogPage /> },
          { path: 'tours/:id', element: <TourDetailsPage /> },
          { path: 'login', element: <LoginPage /> },
          { path: 'register', element: <RegisterPage /> },
          // Orders are a client's (backend require_roles): staff see 403 here.
          { path: 'booking/:tourId', element: <RequireAuth roles={['client']}><BookingPage /></RequireAuth> },
          // Payment (spec 05): the client's own orders only (someone else's is a 404 from the API).
          { path: 'orders/:id/pay', element: <RequireAuth roles={['client']}><PayPage /></RequireAuth> },
          { path: 'payment/success', element: <RequireAuth roles={['client']}><PaymentSuccessPage /></RequireAuth> },
          { path: 'payment/cancel', element: <RequireAuth roles={['client']}><PaymentCancelPage /></RequireAuth> },
          // The client cabinet (spec 06). Only sections with a backend API are listed.
          {
            path: 'cabinet',
            element: <RequireAuth roles={['client']}><CabinetLayout /></RequireAuth>,
            children: [
              { index: true, element: <Navigate to="orders" replace /> },
              { path: 'orders', element: <OrdersPage /> },
              // «Історія подорожей» (spec 08 §4) is the «Завершені» tab of the orders: the same list,
              // with the place and the review state on every card.
              { path: 'history', element: <Navigate to="/cabinet/orders?group=completed" replace /> },
              { path: 'orders/:id', element: <OrderDetailsPage /> },
              { path: 'orders/:id/review', element: <ReviewPage /> },
              // Profile and password (spec 08 §2): GET/PATCH /auth/me, POST /auth/me/password.
              { path: 'profile', element: <ProfilePage /> },
              // Saved tourists for the booking autofill (spec 08 §3): /api/me/passports.
              { path: 'tourists', element: <TouristsPage /> },
              // «Обране» (spec 08 §5): /api/me/favorites.
              { path: 'favorites', element: <FavoritesPage /> },
            ],
          },
          // Static information pages (spec 14): texts in i18n, contacts from the admin's settings.
          { path: 'about', element: <AboutPage /> },
          { path: 'contacts', element: <ContactsPage /> },
          { path: 'terms', element: <TermsPage /> },
          { path: 'privacy', element: <PrivacyPage /> },
          { path: 'faq', element: <FaqPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
      // The back office (spec 09): its own layout, staff only; each section checks its role.
      {
        path: 'office',
        element: <RequireAuth roles={STAFF_ROLES}>{suspended(<OfficeLayout />)}</RequireAuth>,
        children: [
          { index: true, element: <OfficeHome /> },
          {
            path: 'orders',
            element: <RequireOfficeRole role="manager">{suspended(<OfficeOrdersPage />)}</RequireOfficeRole>,
          },
          {
            path: 'orders/:id',
            element: <RequireOfficeRole role="manager">{suspended(<OfficeOrderPage />)}</RequireOfficeRole>,
          },
          ...COMING_SOON.map((section) => ({
            path: section.path,
            element: <RequireOfficeRole role={section.role}><OfficeComingSoon section={section.key} /></RequireOfficeRole>,
          })),
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}
