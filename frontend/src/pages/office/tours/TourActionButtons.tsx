import { ExportOutlined } from '@ant-design/icons'
import { App, Button, Popconfirm, Space, Tooltip } from 'antd'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { tourApi } from '../../../api/officeTours'
import type { TourAction, TourActionInfo } from '../../../api/types'
import { tourActionLabel } from '../../../constants/orderLabels'
import { findTourAction, type TourStateLike } from '../../../features/office/tourActions'
import type { useTourAction } from '../../../features/office/useOfficeAction'

type Runner = ReturnType<typeof useTourAction>

/** The status actions in the order they are shown; «Редагувати» is the page's own link. */
const STATUS_ACTIONS: TourAction[] = ['publish', 'unpublish', 'restore', 'copy', 'archive']

interface Props {
  tour: TourStateLike
  action: Runner
  /** «Копіювати» opens the page's dialog (it asks for the new dates). */
  onCopy: (tour: TourStateLike) => void
  size?: 'small' | 'middle'
}

/**
 * The status buttons of a tour (spec 10), exactly the ones the API lists in `tour_actions`: an
 * allowed action is a button, a refused one is disabled and described by the server's reason
 * (a tooltip plus a hidden text for screen readers). Publish, unpublish, restore and archive
 * ask first; the unpublish and archive questions name the bookings the server counted
 * (`active_bookings`, `archive_cancels`). Nothing here reads the status.
 */
export function TourActionButtons({ tour, action, onCopy, size = 'small' }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const baseId = useId()
  const busy = action.busy !== null
  const listed = STATUS_ACTIONS.map((name) => findTourAction(tour, name)).filter((a): a is TourActionInfo => !!a)

  const run = (name: Exclude<TourAction, 'copy' | 'edit'>) =>
    action.run(`${name}-${tour.id}`, () => tourApi[name](tour.id)).then((result) => {
      if (result) void message.success(t(`office.tours.done.${name}`, { title: tour.title_uk }))
    })

  const confirmText = (name: TourAction): { title: string; description: string } => {
    switch (name) {
      case 'unpublish':
        return {
          title: t('office.tours.confirm.unpublish'),
          description: tour.active_bookings > 0
            ? t('office.tours.confirm.unpublishBookings', { count: tour.active_bookings })
            : t('office.tours.confirm.unpublishText'),
        }
      case 'archive':
        return {
          title: t('office.tours.confirm.archive'),
          description: tour.archive_cancels > 0
            ? t('office.tours.confirm.archiveBookings', { count: tour.archive_cancels })
            : t('office.tours.confirm.archiveText'),
        }
      case 'restore':
        return { title: t('office.tours.confirm.restore'), description: t('office.tours.confirm.restoreText') }
      default:
        return { title: t('office.tours.confirm.publish'), description: t('office.tours.confirm.publishText') }
    }
  }

  const button = (info: TourActionInfo) => {
    const label = tourActionLabel(t, info.action)
    const reasonId = `${baseId}-${info.action}`
    const disabled = !info.allowed || busy
    const common = {
      size, disabled, loading: action.busy === `${info.action}-${tour.id}`,
      'aria-describedby': info.allowed ? undefined : reasonId,
      'aria-label': `${label}: ${tour.title_uk}`,
    }
    let control
    if (info.action === 'copy') {
      control = <Button {...common} onClick={() => onCopy(tour)}>{label}</Button>
    } else {
      const name = info.action as Exclude<TourAction, 'copy' | 'edit'>
      const { title, description } = confirmText(name)
      control = (
        <Popconfirm title={title} description={<span className="office-confirm-text">{description}</span>}
          okText={label} cancelText={t('office.tours.confirm.cancel')} disabled={disabled}
          okButtonProps={{ danger: name === 'archive' }} onConfirm={() => run(name)}>
          <Button {...common} danger={name === 'archive'} type={name === 'publish' ? 'primary' : 'default'}>{label}</Button>
        </Popconfirm>
      )
    }
    if (info.allowed) return <span key={info.action}>{control}</span>
    // A disabled button gets no pointer events: the tooltip sits on a wrapper.
    return (
      <Tooltip key={info.action} title={info.reason}>
        <span className="office-disabled-wrap">
          {control}
          <span id={reasonId} className="visually-hidden">{info.reason}</span>
        </span>
      </Tooltip>
    )
  }

  return (
    <Space wrap size={[8, 8]}>
      {listed.map(button)}
      {tour.for_sale && (
        <Button size={size} href={`/tours/${tour.id}`} target="_blank" rel="noopener noreferrer"
          icon={<ExportOutlined aria-hidden />} aria-label={`${t('office.tours.viewOnSite')}: ${tour.title_uk} ${t('office.tours.newTab')}`}>
          {t('office.tours.viewOnSite')}
        </Button>
      )}
    </Space>
  )
}
