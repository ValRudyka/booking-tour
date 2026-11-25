import { StarFilled, StarOutlined } from '@ant-design/icons'

interface Props {
  value: number
  /** Show empty stars up to this number (ratings); leave out for hotel stars. */
  outOf?: number
  /** What a screen reader says instead of the icons, e.g. «5 зірок». */
  label: string
}

/** Stars as one image for assistive technology (not antd Rate: a disabled Rate is still announced
 * as a group of radio buttons). */
export function StarIcons({ value, outOf, label }: Props) {
  return (
    <span role="img" aria-label={label} className="star-icons">
      {Array.from({ length: value }, (_, i) => <StarFilled key={`f${i}`} aria-hidden />)}
      {outOf !== undefined && Array.from({ length: Math.max(outOf - value, 0) }, (_, i) => (
        <StarOutlined key={`o${i}`} aria-hidden />
      ))}
    </span>
  )
}
