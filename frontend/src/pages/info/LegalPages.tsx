import { Trans, useTranslation } from 'react-i18next'
import { PRIVACY_SECTIONS, TERMS_SECTIONS } from './infoContent'
import { InfoPage, InfoSection } from './InfoPage'
import { RICH_TEXT } from './richText'

/** /terms: short demo text of the booking rules as the backend applies them (spec 14 §1). The
 * offer consent of booking step 4 links here. */
export function TermsPage() {
  const { t } = useTranslation()
  return (
    <InfoPage title={t('info.terms.title')} demoNote>
      {TERMS_SECTIONS.map((key) => (
        <InfoSection key={key} title={t(`info.terms.sections.${key}.title`)}>
          <Trans i18nKey={`info.terms.sections.${key}.text`} components={RICH_TEXT} />
        </InfoSection>
      ))}
    </InfoPage>
  )
}

/** /privacy: what personal data the site keeps, why and who sees it (demo text). */
export function PrivacyPage() {
  const { t } = useTranslation()
  return (
    <InfoPage title={t('info.privacy.title')} demoNote>
      {PRIVACY_SECTIONS.map((key) => (
        <InfoSection key={key} title={t(`info.privacy.sections.${key}.title`)}>
          <Trans i18nKey={`info.privacy.sections.${key}.text`} components={RICH_TEXT} />
        </InfoSection>
      ))}
    </InfoPage>
  )
}
