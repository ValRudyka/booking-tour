import { ClockCircleOutlined } from '@ant-design/icons'
import { Alert } from 'antd'
import { useTranslation } from 'react-i18next'
import { formatKyivTime } from '../../utils/format'
import { SECONDS_PHASE_MS } from './holdClock'

/** «Місця утримуються до 14:35 (залишилось 12 хв)» above the form while seats are held. */
export function HoldTimer({ expiresAt, remaining }: { expiresAt: string; remaining: number }) {
  const { t } = useTranslation()
  const time = formatKyivTime(expiresAt)
  const lastMinutes = remaining <= SECONDS_PHASE_MS
  const seconds = Math.max(0, Math.ceil(remaining / 1000))
  const text = lastMinutes
    ? t('checkout.hold.seconds', { time, left: `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` })
    : t('checkout.hold.minutes', { time, minutes: Math.ceil(remaining / 60_000) })
  // role="timer": a countdown whose every change is NOT read out (its implicit aria-live is off);
  // the form stays usable with a screen reader while the seconds run.
  return (
    <Alert className="booking-hold" type={lastMinutes ? 'warning' : 'info'} showIcon
      icon={<ClockCircleOutlined aria-hidden />} role="timer" title={text} />
  )
}
