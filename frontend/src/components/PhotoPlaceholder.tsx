import { PictureOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import './PhotoPlaceholder.css'

/** Neutral stand-in when a tour has no photo (catalog card, tour gallery). No external images. */
export function PhotoPlaceholder({ height = 180, className }: { height?: number; className?: string }) {
  const { t } = useTranslation()
  return (
    <div className={['photo-placeholder', className].filter(Boolean).join(' ')} style={{ height }}
      role="img" aria-label={t('tour.noPhoto')}>
      <PictureOutlined aria-hidden />
    </div>
  )
}
