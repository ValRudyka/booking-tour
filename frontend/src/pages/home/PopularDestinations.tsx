import { EnvironmentOutlined } from '@ant-design/icons'
import { Card, Skeleton, Typography } from 'antd'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ApiErrorState } from '../../components/ApiErrorState'
import { isMaintenance } from './homeErrors'
import { catalogUrl } from './homeSearch'
import { useDestinations } from './useDestinations'

const SKELETON_COUNT = 6

/** Countries as cards; a click opens the catalog filtered by that country (spec §2). */
export function PopularDestinations() {
  const { t } = useTranslation()
  const headingId = useId()
  const { destinations, isPending, error, retry } = useDestinations()

  // The tour blocks already show the maintenance screen; with no tours there is nothing to list.
  if (error && isMaintenance(error)) return null
  if (!isPending && !error && destinations.length === 0) return null

  let body
  if (isPending) {
    body = (
      <ul className="home-destinations" aria-hidden>
        {Array.from({ length: SKELETON_COUNT }, (_, index) => (
          <li key={index}><Card size="small"><Skeleton active={false} title={false} paragraph={{ rows: 2 }} /></Card></li>
        ))}
      </ul>
    )
  } else if (error) {
    body = <ApiErrorState error={error} onRetry={retry} title={t('home.destinations.loadFailed')} />
  } else {
    body = (
      <ul className="home-destinations">
        {destinations.map(({ country, tours }) => (
          <li key={country.id}>
            <Link to={catalogUrl({ country_id: country.id })} className="home-destination-link">
              <Card size="small" hoverable className="home-destination">
                <span className="home-destination-name">
                  <EnvironmentOutlined aria-hidden /> {country.name_uk}
                </span>{' '}
                <Typography.Text type="secondary">{t('home.destinations.tours', { count: tours })}</Typography.Text>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <section aria-labelledby={headingId} aria-busy={isPending}>
      <h2 id={headingId} className="home-block-title home-block-header">{t('home.destinations.title')}</h2>
      {body}
    </section>
  )
}
