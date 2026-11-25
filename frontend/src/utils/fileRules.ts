import type { TFunction } from 'i18next'
import type { UploadLimits } from '../api/types'

// Client-side checks of an upload against the limits the backend sends (UploadLimitsOut: count,
// size, extensions). Only a convenience: the server checks again, including the file contents
// (magic bytes), and its message is shown if it refuses.

const NAMES: Record<string, { extensions: string[]; mime: string }> = {
  pdf: { extensions: ['pdf'], mime: 'application/pdf' },
  jpg: { extensions: ['jpg', 'jpeg'], mime: 'image/jpeg' },
  png: { extensions: ['png'], mime: 'image/png' },
}

/** The `accept` attribute of the file input: extensions and MIME types of the allowed formats. */
export function acceptOf(limits: UploadLimits): string {
  return limits.file_types.flatMap((type) => {
    const known = NAMES[type]
    return known ? [...known.extensions.map((ext) => `.${ext}`), known.mime] : [`.${type}`]
  }).join(',')
}

/** "PDF, JPG" for hints and messages. */
export function typesText(limits: UploadLimits): string {
  return limits.file_types.map((type) => type.toUpperCase()).join(', ')
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
}

/** Why this file cannot be added (type or size), or null. The count is checked by the caller. */
export function fileProblem(t: TFunction, file: File, limits: UploadLimits): string | null {
  const ext = extensionOf(file.name)
  const allowed = limits.file_types.some((type) => {
    const known = NAMES[type]
    if (!known) return ext === type
    // The extension decides; a browser-reported MIME type, when present, must match too.
    return known.extensions.includes(ext) && (!file.type || file.type === known.mime)
  })
  if (!allowed) return t('cabinet.files.wrongType', { name: file.name, types: typesText(limits) })
  if (file.size > limits.max_file_mb * 1024 * 1024) {
    return t('cabinet.files.tooBig', { name: file.name, mb: limits.max_file_mb })
  }
  return null
}
