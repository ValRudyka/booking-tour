import { HeartFilled, HeartOutlined } from '@ant-design/icons'
import { App, Button } from 'antd'
import { useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { useFavoriteIds, useToggleFavorite } from '../api/favorites'
import { AuthContext } from '../features/auth/authContext'
import { loginPath } from '../features/auth/redirect'
import './FavoriteButton.css'

interface Props {
  tourId: number
  title: string
  /** `icon`: a round heart over a catalog card's photo; `button`: «В обране» on the tour page. */
  variant?: 'icon' | 'button'
}

/**
 * «В обране» (spec 08 §5). A client toggles the tour in «Обране»; a guest is sent to sign in and
 * comes back to this page; staff have no «Обране» (the API is client-only), so they see nothing.
 * Outside the auth provider (a card rendered on its own) nothing is shown either.
 */
export function FavoriteButton({ tourId, title, variant = 'icon' }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const auth = useContext(AuthContext)
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const isClient = auth?.user?.role === 'client'
  const ids = useFavoriteIds(isClient)
  const toggle = useToggleFavorite()

  if (!auth || auth.status === 'loading' || (auth.user && !isClient)) return null
  const active = isClient && (ids.data ?? []).includes(tourId)

  const onClick = () => {
    if (!isClient) {
      navigate(loginPath(`${pathname}${search}`))
      return
    }
    toggle.mutate({ tourId, add: !active }, {
      onError: (error) => {
        // 404: the tour has just left the catalog; 422: the limit of the list. Both are Ukrainian texts.
        void message.error(error instanceof ApiError && error.detail ? error.detail : t('errors.generic'))
      },
    })
  }

  const icon = active ? <HeartFilled aria-hidden className="favorite-heart-on" /> : <HeartOutlined aria-hidden />
  const label = t(active ? 'favorites.removeOf' : 'favorites.addOf', { title })
  if (variant === 'button') {
    return (
      <Button block icon={icon} aria-pressed={active} aria-label={label} onClick={onClick}>
        {t(active ? 'favorites.inFavorites' : 'favorites.add')}
      </Button>
    )
  }
  return (
    <Button shape="circle" className="favorite-icon" icon={icon} aria-pressed={active} aria-label={label}
      title={label} onClick={onClick} />
  )
}
