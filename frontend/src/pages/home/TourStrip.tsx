import { ArrowRightOutlined } from '@ant-design/icons'
import { Col, Empty, Flex, Row } from 'antd'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { useTours } from '../../api/catalog'
import type { TourSearchParams } from '../../api/types'
import { ApiErrorState } from '../../components/ApiErrorState'
import { AppLink } from '../../components/AppLink'
import { TourCard } from '../../components/TourCard'
import { TourCardSkeleton } from '../../components/TourCardSkeleton'
import { isMaintenance } from './homeErrors'

const CARD_COLS = { xs: 24, sm: 12, xl: 6 } as const // 4 cards, then 2, then 1 per row

interface Props {
  title: string
  params: TourSearchParams
  /** Link under the heading, e.g. «Усі тури» -> /tours. */
  allLink?: { to: string; label: string }
  /** An optional block («Гарячі пропозиції») disappears when it has nothing to show. */
  optional?: boolean
  /** Shown when a required block has no tours. */
  emptyText?: string
}

/**
 * A home page block with up to 4 tour cards. It has its own query, skeleton and error, so a
 * failure here never breaks the other blocks (spec §3). In maintenance mode every request fails
 * the same way: an optional block then hides itself and the required one shows the maintenance
 * screen, so the page has it once and not once per block.
 */
export function TourStrip({ title, params, allLink, optional = false, emptyText }: Props) {
  const { t } = useTranslation()
  const headingId = useId()
  const tours = useTours(params)

  if (optional && tours.isError && isMaintenance(tours.error)) return null
  if (optional && tours.isSuccess && tours.data.items.length === 0) return null

  let body
  if (tours.isPending) {
    body = (
      <Row gutter={[16, 16]}>
        {Array.from({ length: params.page_size ?? 4 }, (_, index) => (
          <Col key={index} {...CARD_COLS}><TourCardSkeleton /></Col>
        ))}
      </Row>
    )
  } else if (tours.isError) {
    body = <ApiErrorState error={tours.error} onRetry={() => void tours.refetch()} title={t('errors.loadFailed')} />
  } else if (tours.data.items.length === 0) {
    body = <Empty description={emptyText} />
  } else {
    body = (
      <Row gutter={[16, 16]}>
        {tours.data.items.map((tour) => (
          <Col key={tour.id} {...CARD_COLS}><TourCard tour={tour} headingLevel={3} /></Col>
        ))}
      </Row>
    )
  }

  return (
    <section aria-labelledby={headingId} aria-busy={tours.isPending}>
      <Flex justify="space-between" align="baseline" wrap gap={8} className="home-block-header">
        <h2 id={headingId} className="home-block-title">{title}</h2>
        {allLink && (
          <AppLink to={allLink.to}>
            {allLink.label} <ArrowRightOutlined aria-hidden />
          </AppLink>
        )}
      </Flex>
      {body}
    </section>
  )
}
