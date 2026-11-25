import { Result } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'
import type { UserRole } from '../../api/types'
import { useAuth } from '../../features/auth/useAuth'
import { officeHome, type OfficeSectionKey } from '../../features/office/menu'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

/** /office: straight to the first section of the user's role. */
export function OfficeHome() {
  const { user } = useAuth()
  const home = user ? officeHome(user.role) : null
  return home ? <Navigate to={home} replace /> : <OfficeForbidden />
}

/** A section whose page comes with a later spec (features/office/menu.ts, `built: false`). */
export function OfficeComingSoon({ section }: { section: OfficeSectionKey }) {
  const { t } = useTranslation()
  const title = t(`office.section.${section}`)
  useDocumentTitle(title)
  return (
    <Result status="info" title={<h1 className="result-title">{title}</h1>} subTitle={t('office.comingSoon')} />
  )
}

/** 403 inside the back office: the page or the API refused this role. */
export function OfficeForbidden() {
  const { t } = useTranslation()
  useDocumentTitle(t('office.forbiddenTitle'))
  return (
    <Result status="403" title={<h1 className="result-title">{t('office.forbiddenTitle')}</h1>}
      subTitle={t('office.forbiddenText')} />
  )
}

/** A back-office page of one role; another staff role sees the 403 inside the layout. The
 * backend checks the role again on every request (require_roles). */
export function RequireOfficeRole({ role, children }: { role: UserRole; children: ReactNode }) {
  const { user } = useAuth()
  return user?.role === role ? <>{children}</> : <OfficeForbidden />
}
