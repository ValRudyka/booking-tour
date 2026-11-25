import { ClockCircleOutlined } from '@ant-design/icons'
import { Button, Result, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { ApiError } from '../../api/client'
import { useTour } from '../../api/tour'
import { ApiErrorState } from '../../components/ApiErrorState'
import { BackToCatalogButton } from '../../components/BackToCatalogButton'
import { CLIENT_HOME } from '../../features/auth/redirect'

export function MyOrdersButton({ primary = false }: { primary?: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return <Button type={primary ? 'primary' : 'default'} onClick={() => navigate(CLIENT_HOME)}>{t('payment.myOrders')}</Button>
}

/** «Забронювати знову» to the tour page while the tour is still for sale (its page is a 404
 * otherwise, CLAUDE.md), else «До каталогу». */
export function RebookButton({ tourId }: { tourId: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const tour = useTour(tourId)
  if (tour.isSuccess) {
    return <Button type="primary" onClick={() => navigate(`/tours/${tourId}`)}>{t('payment.rebook')}</Button>
  }
  return <BackToCatalogButton />
}

export function PageResult({ status, title, text, extra, icon }: {
  status?: 'success' | 'info' | 'warning' | '404'
  title: string
  text?: ReactNode
  extra?: ReactNode
  icon?: ReactNode
}) {
  return <Result status={status} icon={icon} title={<h1 className="result-title">{title}</h1>} subTitle={text} extra={extra} />
}

export function OrderNotFound() {
  const { t } = useTranslation()
  return <PageResult status="404" title={t('payment.states.notFoundTitle')} text={t('payment.states.notFoundText')}
    extra={<MyOrdersButton primary />} />
}

/** Loading / 404 / error of the order query, shared by the three payment pages. */
export function OrderQueryState({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
  const { t } = useTranslation()
  if (!error) return <Skeleton active={false} paragraph={{ rows: 6 }} />
  if (error instanceof ApiError && error.kind === 'not_found') return <OrderNotFound />
  return <ApiErrorState error={error} onRetry={onRetry} title={t('payment.states.loadFailed')} />
}

/** «Перевіряємо оплату…»: a static clock icon, no Spin (no animations, design rules). */
export function CheckingResult() {
  const { t } = useTranslation()
  return <PageResult icon={<ClockCircleOutlined aria-hidden />} title={t('payment.success.checkingTitle')}
    text={t('payment.success.checkingText')} />
}
