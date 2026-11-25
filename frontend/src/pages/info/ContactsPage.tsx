import { MailOutlined, PhoneOutlined } from '@ant-design/icons'
import { Alert, Skeleton, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { useSiteContacts } from '../../api/site'
import { ApiErrorState } from '../../components/ApiErrorState'
import { AppLink } from '../../components/AppLink'
import { CONTACTS_FAQ } from './infoContent'
import { InfoPage, InfoSection } from './InfoPage'

/** /contacts: the support phone and e-mail from the admin's settings (GET /site/contacts, form
 * 4.6.4.1 fields 8–9), never from the code. Empty fields are not shown. No embedded maps. */
export function ContactsPage() {
  const { t } = useTranslation()
  const contacts = useSiteContacts()
  const phone = contacts.data?.phone
  const email = contacts.data?.email

  let body
  if (contacts.isPending) {
    body = <Skeleton active={false} title={false} paragraph={{ rows: 2 }} />
  } else if (contacts.isError) {
    body = <ApiErrorState error={contacts.error} onRetry={() => void contacts.refetch()}
      title={t('info.contacts.loadFailed')} />
  } else if (!phone && !email) {
    body = <Alert type="info" title={t('info.contacts.empty')} />
  } else {
    body = (
      <Space orientation="vertical" size={8} className="info-contacts">
        {phone && (
          <Typography.Text>
            <PhoneOutlined aria-hidden /> {t('footer.phone')}: <a href={`tel:${phone}`}>{phone}</a>
          </Typography.Text>
        )}
        {email && (
          <Typography.Text>
            <MailOutlined aria-hidden /> {t('footer.email')}: <a href={`mailto:${email}`}>{email}</a>
          </Typography.Text>
        )}
      </Space>
    )
  }

  return (
    <InfoPage title={t('info.contacts.title')} lead={t('info.contacts.lead')}>
      <InfoSection title={t('info.contacts.support')}>{body}</InfoSection>
      <InfoSection title={t('info.contacts.faqTitle')}>
        <ul className="info-list">
          {CONTACTS_FAQ.map((key) => (
            <li key={key}><AppLink to={`/faq#${key}`}>{t(`info.faq.items.${key}.q`)}</AppLink></li>
          ))}
          <li><AppLink to="/faq">{t('info.contacts.allFaq')}</AppLink></li>
        </ul>
      </InfoSection>
    </InfoPage>
  )
}
