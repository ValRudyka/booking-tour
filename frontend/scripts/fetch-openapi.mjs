// Saves the backend's OpenAPI schema as src/api/openapi.json (pretty-printed, so API changes show
// up as readable diffs). `npm run gen:api` then generates src/api/schema.d.ts from this file, and
// tests read the status enums from it (src/constants/orderStatus.test.ts): a new backend status
// without a Ukrainian label fails the tests.
import { writeFile } from 'node:fs/promises'

const url = process.env.OPENAPI_URL ?? 'http://127.0.0.1:8000/openapi.json'
const response = await fetch(url)
if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`)
const schema = await response.json()
await writeFile(new URL('../src/api/openapi.json', import.meta.url), `${JSON.stringify(schema, null, 2)}\n`)
console.log(`Saved src/api/openapi.json from ${url}`)
