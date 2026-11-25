import { CreditCardOutlined, FileDoneOutlined, FormOutlined, SearchOutlined } from '@ant-design/icons'
import { Card, theme } from 'antd'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'

// Static text: what the client does, in the order of the booking flow (ТЗ 4.4).
const STEPS = [
  { key: 'choose', Icon: SearchOutlined },
  { key: 'fill', Icon: FormOutlined },
  { key: 'pay', Icon: CreditCardOutlined },
  { key: 'documents', Icon: FileDoneOutlined },
] as const

export function HowToBook() {
  const { t } = useTranslation()
  const { token } = theme.useToken()
  const headingId = useId()
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId} className="home-block-title home-block-header">{t('home.howTo.title')}</h2>
      <ol className="home-steps">
        {STEPS.map(({ key, Icon }, index) => (
          <li key={key}>
            <Card className="home-step">
              <Icon aria-hidden className="home-step-icon" style={{ color: token.colorPrimary }} />
              <h3 className="home-step-title">{index + 1}. {t(`home.howTo.${key}.title`)}</h3>
              <p className="home-step-text">{t(`home.howTo.${key}.text`)}</p>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  )
}
