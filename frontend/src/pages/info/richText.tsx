import { Typography } from 'antd'
import { AppLink } from '../../components/AppLink'

/**
 * Tags allowed in the long texts of the info pages (`<Trans components={RICH_TEXT}>`): paragraphs,
 * lists, bold and internal links. The texts stay in uk.json with their markup, so a translator
 * sees whole sentences; links are router links (no page reload).
 */
export const RICH_TEXT = {
  p: <Typography.Paragraph />,
  ul: <ul className="info-list" />,
  li: <li />,
  strong: <strong />,
  tours: <AppLink to="/tours" />,
  contacts: <AppLink to="/contacts" />,
  terms: <AppLink to="/terms" />,
  privacy: <AppLink to="/privacy" />,
  faq: <AppLink to="/faq" />,
  faqHold: <AppLink to="/faq#hold" />,
  faqRefund: <AppLink to="/faq#refund" />,
}
