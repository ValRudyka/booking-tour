/** WCAG 2.x contrast ratio helpers (used by tests only). */
type Rgba = { r: number; g: number; b: number; a: number }

export function parseColor(color: string): Rgba {
  const value = color.trim().toLowerCase()
  if (value.startsWith('#')) {
    const hex = value.length === 4
      ? value.slice(1).split('').map((c) => c + c).join('')
      : value.slice(1)
    const alpha = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1
    return { r: parseInt(hex.slice(0, 2), 16), g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16), a: alpha }
  }
  const match = value.match(/rgba?\(([^)]+)\)/)
  if (!match) throw new Error(`Unsupported color: ${color}`)
  const [r, g, b, a = '1'] = match[1].split(',').map((part) => part.trim())
  return { r: Number(r), g: Number(g), b: Number(b), a: Number(a) }
}

/** A semi-transparent foreground as it looks on an opaque background. */
function composite(fg: Rgba, bg: Rgba): Rgba {
  const mix = (f: number, b: number) => f * fg.a + b * (1 - fg.a)
  return { r: mix(fg.r, bg.r), g: mix(fg.g, bg.g), b: mix(fg.b, bg.b), a: 1 }
}

function luminance({ r, g, b }: Rgba): number {
  const channel = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

export function contrastRatio(foreground: string, background: string): number {
  const bg = parseColor(background)
  const fg = composite(parseColor(foreground), bg)
  const [light, dark] = [luminance(fg), luminance(bg)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}
