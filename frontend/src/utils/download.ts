// Saving a file that came from an authorised request (a private order document). The browser
// cannot download it from a plain link, because a link carries no Authorization header.

/** The file name from `Content-Disposition` (the backend builds it, e.g.
 * `attachment; filename="voucher-TU-2026-000022-5.pdf"`; the API exposes the header to CORS). */
export function filenameFromDisposition(header: string | null | undefined): string | null {
  if (!header) return null
  const encoded = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, ''))
    } catch {
      // fall through to the plain name
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1].trim() : null
}

const EXTENSIONS: Record<string, string> = { 'application/pdf': 'pdf', 'image/jpeg': 'jpg', 'image/png': 'png' }

/** A fallback name when the header is missing: "<base>.<ext from the blob type>". */
export function fallbackFilename(base: string, blob: Blob): string {
  const ext = EXTENSIONS[blob.type]
  return ext ? `${base}.${ext}` : base
}

/** Hands the Blob to the browser as a download (a temporary object URL, freed afterwards). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Some browsers start the download after the click handler returns.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
