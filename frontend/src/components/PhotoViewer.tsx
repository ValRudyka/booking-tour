import { Image } from 'antd'
import { cloneElement, isValidElement, useState } from 'react'
import { useTranslation } from 'react-i18next'
import './PhotoViewer.css'

export interface Photo {
  src: string
  alt: string
}

interface Props {
  photos: Photo[]
  /** "gallery": one large photo and thumbnails; "thumbs": thumbnails only (review photos). */
  variant: 'gallery' | 'thumbs'
}

/**
 * Photos that open in antd's fullscreen preview (Image.PreviewGroup with its own navigation).
 * Every photo is a real <button>, so the gallery works from the keyboard; the preview itself is
 * antd's (Esc closes, arrows move), without animations because the theme turns motion off.
 */
export function PhotoViewer({ photos, variant }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState(0)
  const show = (index: number) => {
    setCurrent(index)
    setOpen(true)
  }
  const label = (index: number) => t('tourPage.openPhoto', { n: index + 1, total: photos.length })
  const thumbs = variant === 'gallery' ? photos.slice(1) : photos
  const offset = variant === 'gallery' ? 1 : 0

  return (
    <div className={`photo-viewer photo-viewer-${variant}`}>
      {variant === 'gallery' && (
        <button type="button" className="photo-viewer-main" onClick={() => show(0)} aria-label={label(0)}>
          <img src={photos[0].src} alt={photos[0].alt} />
        </button>
      )}
      {thumbs.length > 0 && (
        <div className="photo-viewer-thumbs">
          {thumbs.map((photo, i) => (
            <button key={photo.src} type="button" className="photo-viewer-thumb"
              onClick={() => show(i + offset)} aria-label={label(i + offset)}>
              <img src={photo.src} alt={photo.alt} loading="lazy" />
            </button>
          ))}
        </div>
      )}
      <Image.PreviewGroup
        items={photos.map((photo) => ({ src: photo.src, alt: photo.alt }))}
        preview={{
          open, current, onOpenChange: (next) => setOpen(next), onChange: (next) => setCurrent(next),
          // @rc-component/image passes the item's alt but then overwrites it with the preview's
          // own (empty) alt prop, so the fullscreen image would have none: put it back.
          imageRender: (node, info) => (isValidElement<{ alt?: string }>(node)
            ? cloneElement(node, { alt: photos[info.current]?.alt }) : node),
        }}
      />
    </div>
  )
}
