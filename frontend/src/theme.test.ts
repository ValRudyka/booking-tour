import { theme } from 'antd'
import { describe, expect, it } from 'vitest'
import { contrastRatio } from './test/contrast'
import { antdTheme, PAGE_BG, PRICE_COLOR, PRIMARY_COLOR, SAND_BG, TEXT_COLOR } from './theme'

// ТЗ §5.3 / CLAUDE.md: text contrast at least 4.5:1. The tokens are the ones antd really
// renders with (derived from our seed tokens), so a future token change is caught here.
const tokens = theme.getDesignToken(antdTheme)
const MIN = 4.5

describe('theme contrast', () => {
  const backgrounds = { white: '#FFFFFF', layout: PAGE_BG }

  it.each([
    ['colorText', tokens.colorText],
    ['colorTextHeading', tokens.colorTextHeading],
    ['colorTextSecondary', tokens.colorTextSecondary],
    ['colorTextTertiary', tokens.colorTextTertiary],
    ['colorTextDescription', tokens.colorTextDescription],
    ['colorTextPlaceholder', tokens.colorTextPlaceholder],
    ['primary (links)', PRIMARY_COLOR],
    ['price', PRICE_COLOR],
    ['colorSuccess', tokens.colorSuccess],
    ['colorWarning', tokens.colorWarning],
    ['colorError', tokens.colorError],
  ])('%s is readable on white and on the page background', (_name, color) => {
    expect(contrastRatio(color, backgrounds.white)).toBeGreaterThanOrEqual(MIN)
    expect(contrastRatio(color, backgrounds.layout)).toBeGreaterThanOrEqual(MIN)
  })

  it('white text on primary buttons is readable', () => {
    expect(contrastRatio('#FFFFFF', tokens.colorPrimary)).toBeGreaterThanOrEqual(MIN)
  })

  it.each([
    ['warning', tokens.colorWarningText, tokens.colorWarningBg],
    ['error', tokens.colorErrorText, tokens.colorErrorBg],
    ['success', tokens.colorSuccessText, tokens.colorSuccessBg],
    ['info', tokens.colorInfoText, tokens.colorInfoBg],
  ])('%s tag/alert text is readable on its own background', (_name, color, bg) => {
    expect(contrastRatio(color, bg)).toBeGreaterThanOrEqual(MIN)
  })

  it('body text is readable on the sand background', () => {
    expect(contrastRatio(TEXT_COLOR, SAND_BG)).toBeGreaterThanOrEqual(MIN)
  })
})
