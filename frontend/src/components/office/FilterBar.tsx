import { ClearOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, DatePicker, Form, Input, Select, Space, Switch } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * The search and filter bar of every back-office list (spec 09 §1; specs 10–13 reuse it): an
 * inline antd Form whose fields are described as data. It works on URL-shaped values (strings,
 * YYYY-MM-DD dates, lists) and never keeps its own state: the page reads them from the URL
 * (features/office/urlState.ts), passes them in and writes the result back. «Знайти» applies,
 * «Скинути» clears every field. Each field has a visible label (ТЗ §5.3).
 */
export type FilterField =
  | { kind: 'text'; name: string; label: string; placeholder?: string; maxLength?: number }
  /** `clears`: fields emptied when this one changes (a resort list that depends on the country). */
  | { kind: 'select'; name: string; label: string; options: { value: string; label: string }[]; multiple?: boolean; clears?: string[] }
  /** Two URL keys, e.g. created_from / created_to. */
  | { kind: 'dateRange'; name: string; label: string; from: string; to: string }
  /** `true` in the URL when on. */
  | { kind: 'switch'; name: string; label: string }

/** Values by URL key: text, a date, 'true' for a switch, a list for a multiple select. */
export type FilterValues = Record<string, string | string[] | undefined>

type FormValues = Record<string, string | string[] | boolean | [Dayjs | null, Dayjs | null] | null | undefined>

const DATE = 'YYYY-MM-DD'

function toForm(fields: FilterField[], values: FilterValues): FormValues {
  const form: FormValues = {}
  for (const field of fields) {
    if (field.kind === 'dateRange') {
      const from = values[field.from]
      const to = values[field.to]
      form[field.name] = from || to
        ? [typeof from === 'string' ? dayjs(from) : null, typeof to === 'string' ? dayjs(to) : null]
        : null
    } else if (field.kind === 'switch') {
      form[field.name] = values[field.name] === 'true'
    } else if (field.kind === 'select' && field.multiple) {
      const value = values[field.name]
      form[field.name] = Array.isArray(value) ? value : value ? [value] : []
    } else {
      form[field.name] = values[field.name] ?? undefined
    }
  }
  return form
}

function fromForm(fields: FilterField[], form: FormValues): FilterValues {
  const values: FilterValues = {}
  for (const field of fields) {
    const value = form[field.name]
    if (field.kind === 'dateRange') {
      const [from, to] = Array.isArray(value) ? value as [Dayjs | null, Dayjs | null] : [null, null]
      values[field.from] = from ? from.format(DATE) : undefined
      values[field.to] = to ? to.format(DATE) : undefined
    } else if (field.kind === 'switch') {
      values[field.name] = value ? 'true' : undefined
    } else if (Array.isArray(value)) {
      values[field.name] = value.length > 0 ? value as string[] : undefined
    } else {
      const text = typeof value === 'string' ? value.trim() : ''
      values[field.name] = text || undefined
    }
  }
  return values
}

interface Props {
  fields: FilterField[]
  values: FilterValues
  onApply: (values: FilterValues) => void
  /** Accessible name of the form, e.g. «Пошук і фільтри». */
  label?: string
  /** The values while the user edits them (before «Знайти»), e.g. to load dependent options. */
  onDraftChange?: (values: FilterValues) => void
}

export function FilterBar({ fields, values, onApply, label, onDraftChange }: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<FormValues>()

  // The URL is the state: going back in history or a link changes the fields too.
  // Only a change of the values themselves (compared by content) is applied, so new option
  // lists (a resort list loaded for the country being chosen) never overwrite what the user is
  // typing or choosing.
  const fieldsRef = useRef(fields)
  useEffect(() => { fieldsRef.current = fields })
  const key = JSON.stringify(values)
  useEffect(() => {
    form.setFieldsValue(toForm(fieldsRef.current, JSON.parse(key) as FilterValues))
  }, [form, key])

  const reset = () => {
    const empty = toForm(fields, {})
    form.setFieldsValue(empty)
    onApply(fromForm(fields, empty))
  }

  return (
    <Form form={form} layout="inline" className="office-filter-bar" aria-label={label ?? t('office.filters.title')}
      initialValues={toForm(fields, values)} onFinish={(form) => onApply(fromForm(fields, form))}
      onValuesChange={(changed: FormValues) => {
        for (const field of fields) {
          if (field.kind === 'select' && field.clears && field.name in changed) {
            form.setFieldsValue(Object.fromEntries(field.clears.map((name) => [name, undefined])))
          }
        }
        onDraftChange?.(fromForm(fields, form.getFieldsValue()))
      }}>
      {fields.map((field) => (
        <Form.Item key={field.name} name={field.name} label={field.label}
          valuePropName={field.kind === 'switch' ? 'checked' : 'value'}>
          {field.kind === 'text' ? (
            <Input allowClear placeholder={field.placeholder} maxLength={field.maxLength ?? 100} className="office-filter-text" />
          ) : field.kind === 'select' ? (
            <Select allowClear mode={field.multiple ? 'multiple' : undefined} options={field.options}
              placeholder={t('office.filters.any')} className="office-filter-select" maxTagCount="responsive" />
          ) : field.kind === 'dateRange' ? (
            <DatePicker.RangePicker allowEmpty={[true, true]} format="DD.MM.YYYY"
              placeholder={[t('office.filters.from'), t('office.filters.to')]} />
          ) : (
            <Switch />
          )}
        </Form.Item>
      ))}
      <Form.Item>
        <Space>
          <Button type="primary" htmlType="submit" icon={<SearchOutlined aria-hidden />}>{t('office.filters.search')}</Button>
          <Button onClick={reset} icon={<ClearOutlined aria-hidden />}>{t('office.filters.reset')}</Button>
        </Space>
      </Form.Item>
    </Form>
  )
}
