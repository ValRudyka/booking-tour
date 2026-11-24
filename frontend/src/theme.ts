import type { ThemeConfig } from 'antd'

/** "Sea and sand" palette (CLAUDE.md, ТЗ §5.3). */
export const PRIMARY_COLOR = '#0E7490'
/** Prices and discounts only — never buttons. */
export const PRICE_COLOR = '#C2410C'
/** Large background areas only (hero, sections) — never text or small elements. */
export const SAND_BG = '#F2E8D5'
export const TEXT_COLOR = '#0F172A'
export const PAGE_BG = '#F8FAFC'

export const antdTheme: ThemeConfig = {
  token: {
    colorPrimary: PRIMARY_COLOR,
    colorSuccess: '#15803D',
    colorWarning: '#B45309',
    colorError: '#B91C1C',
    colorTextBase: TEXT_COLOR,
    colorBgLayout: PAGE_BG,
    borderRadius: 6,
    motion: false, // no animations (design rules)
    // antd derives secondary/description/placeholder text from colorTextBase with 65/45/25 %
    // opacity; 45 % and 25 % fall below the 4.5:1 contrast the ТЗ §5.3 requires, so these
    // are set to solid slate shades instead (checked in theme.test.ts).
    colorTextSecondary: '#334155',
    colorTextTertiary: '#475569',
    colorTextDescription: '#475569',
    colorTextPlaceholder: '#64748B',
    // Status colours: info follows the primary colour instead of antd's default blue, and the
    // light backgrounds of Alert/Tag are set by hand because the derived ones were too dark
    // for the status text on top of them (success 2.6:1, warning 4.3:1).
    colorInfo: PRIMARY_COLOR,
    colorSuccessBg: '#F0FDF4',
    colorWarningBg: '#FFFBEB',
    colorErrorBg: '#FEF2F2',
    colorInfoBg: '#ECFEFF',
  },
  components: {
    // A light header and footer instead of antd's dark default.
    Layout: { headerBg: '#FFFFFF', headerPadding: '0 16px', footerBg: '#FFFFFF', footerPadding: '24px 16px' },
  },
}
