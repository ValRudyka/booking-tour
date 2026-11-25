import { Result, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useLocation } from 'react-router'
import type { UserRole } from '../../api/types'
import { BackToCatalogButton } from '../../components/BackToCatalogButton'
import { loginPath } from './redirect'
import { useAuth } from './useAuth'

/**
 * A page for signed-in users only. A guest goes to /login and comes back afterwards
 * (?redirect=); a signed-in user with another role sees 403. Rights are checked again by the
 * backend on every request (require_roles), this only spares the visitor a broken page.
 */
export function RequireAuth({ roles, children }: { roles?: readonly UserRole[]; children: ReactNode }) {
  const { t } = useTranslation()
  const { user, status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <Skeleton active={false} paragraph={{ rows: 4 }} />
  if (!user) return <Navigate to={loginPath(`${location.pathname}${location.search}`)} replace />
  if (roles && !roles.includes(user.role)) {
    return (
      <Result status="403" title={<h1 className="result-title">{t('auth.forbiddenTitle')}</h1>}
        subTitle={t('auth.forbiddenText')} extra={<BackToCatalogButton />} />
    )
  }
  return <>{children}</>
}
