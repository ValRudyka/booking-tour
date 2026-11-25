import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import { fallbackFilename, filenameFromDisposition } from './download'
import { acceptOf, fileProblem, typesText } from './fileRules'

const LIMITS = { max_files: 3, max_file_mb: 1, file_types: ['jpg', 'pdf'] }
const t = i18n.t.bind(i18n)

describe('download names', () => {
  it.each([
    ['attachment; filename="voucher-TU-1-5.pdf"', 'voucher-TU-1-5.pdf'],
    ['attachment; filename=voucher.pdf', 'voucher.pdf'],
    ["attachment; filename*=UTF-8''%D0%B2%D0%B0%D1%83%D1%87%D0%B5%D1%80.pdf", 'ваучер.pdf'],
    [null, null],
  ])('%s -> %s', (header, name) => {
    expect(filenameFromDisposition(header)).toBe(name)
  })

  it('falls back to a name with the extension of the file type', () => {
    expect(fallbackFilename('voucher-TU-1', new Blob([''], { type: 'application/pdf' }))).toBe('voucher-TU-1.pdf')
    expect(fallbackFilename('doc', new Blob(['']))).toBe('doc')
  })
})

describe('upload rules from the API', () => {
  it('builds the accept list and the hint from the extensions', () => {
    expect(acceptOf(LIMITS)).toBe('.jpg,.jpeg,image/jpeg,.pdf,application/pdf')
    expect(typesText(LIMITS)).toBe('JPG, PDF')
  })

  it('accepts an allowed file and refuses other types and big files', () => {
    expect(fileProblem(t, new File(['x'], 'scan.JPEG', { type: 'image/jpeg' }), LIMITS)).toBeNull()
    expect(fileProblem(t, new File(['x'], 'scan.png', { type: 'image/png' }), LIMITS))
      .toBe('Файл «scan.png»: дозволені формати JPG, PDF')
    expect(fileProblem(t, new File([new Uint8Array(1024 * 1024 + 1)], 'big.pdf', { type: 'application/pdf' }), LIMITS))
      .toBe('Файл «big.pdf» більший за 1 МБ')
  })
})
