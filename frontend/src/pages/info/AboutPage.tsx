import { Trans, useTranslation } from 'react-i18next'
import { ABOUT_SECTIONS } from './infoContent'
import { InfoPage, InfoSection } from './InfoPage'
import { RICH_TEXT } from './richText'

/** /about: what the site does; a course project, so no company details are invented. */
export function AboutPage() {
  const { t } = useTranslation()
  return (
    <InfoPage title={t('info.about.title')} lead={t('info.about.lead')}>
      {ABOUT_SECTIONS.map((key) => (
        <InfoSection key={key} title={t(`info.about.sections.${key}.title`)}>
          <Trans i18nKey={`info.about.sections.${key}.text`} components={RICH_TEXT} />
        </InfoSection>
      ))}
    </InfoPage>
  )
}
