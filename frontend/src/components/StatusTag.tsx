import { Tag } from 'antd'
import { useTranslation } from 'react-i18next'
import { statusLabel, statusTone, TAG_COLORS, type StatusByKind, type StatusKind } from '../constants/orderStatus'

/** A status from the one dictionary (constants/orderStatus.ts) as a coloured tag. */
export function StatusTag<K extends StatusKind>({ kind, status }: { kind: K; status: StatusByKind[K] }) {
  const { t } = useTranslation()
  return (
    <Tag color={TAG_COLORS[statusTone(kind, status)]} data-status={status}>
      {statusLabel(t, kind, status)}
    </Tag>
  )
}
