import { InfoCircleOutlined } from '@ant-design/icons'
import { Alert, Typography } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import './info.css'

interface Props {
  title: string
  lead?: ReactNode
  /** «Навчальний проєкт. Цей текст не є юридичним документом.» (terms and privacy). */
  demoNote?: boolean
  children: ReactNode
}

/** Shell of the static pages (spec 14 §1): one h1, text up to ~760 px wide for reading. */
export function InfoPage({ title, lead, demoNote = false, children }: Props) {
  const { t } = useTranslation()
  useDocumentTitle(title)
  return (
    <article className="info-page">
      <Typography.Title level={1} className="info-title">{title}</Typography.Title>
      {demoNote && (
        <Alert type="info" showIcon icon={<InfoCircleOutlined aria-hidden />} className="info-demo-note"
          title={t('info.demoNote')} description={t('info.demoNoteText')} />
      )}
      {lead && <Typography.Paragraph className="info-lead">{lead}</Typography.Paragraph>}
      {children}
    </article>
  )
}

/** One h2 section of an info page. */
export function InfoSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="info-section">
      <Typography.Title level={2} className="info-section-title">{title}</Typography.Title>
      {children}
    </section>
  )
}
