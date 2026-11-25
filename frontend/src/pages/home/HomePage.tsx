import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { HomeBanner } from './HomeBanner'
import { HOT_PARAMS, NEAREST_PARAMS } from './homeSearch'
import { TourStrip } from './TourStrip'
import './HomePage.css'

/** / — the home page (spec 07-home-page.md). Every block loads and fails on its own. */
export function HomePage() {
  const { t } = useTranslation()
  useDocumentTitle('') // just the site name
  return (
    <div className="home-page">
      <HomeBanner />
      <TourStrip title={t('home.hot.title')} params={HOT_PARAMS} optional />
      <TourStrip title={t('home.nearest.title')} params={NEAREST_PARAMS}
        allLink={{ to: '/tours', label: t('home.nearest.all') }} emptyText={t('home.nearest.empty')} />
    </div>
  )
}
