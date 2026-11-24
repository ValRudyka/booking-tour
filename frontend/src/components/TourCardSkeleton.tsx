import { Card, Skeleton } from 'antd'

/** Loading placeholder in the shape of a TourCard; static (no animations). */
export function TourCardSkeleton() {
  return (
    <Card cover={<Skeleton.Node active={false} style={{ width: '100%', height: 180 }} />}
      aria-hidden data-testid="tour-card-skeleton">
      <Skeleton active={false} title paragraph={{ rows: 4 }} />
    </Card>
  )
}
