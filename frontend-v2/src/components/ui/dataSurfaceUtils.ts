export type DataRecord = Record<string, unknown>

export function asArray<T = DataRecord>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object') {
    const record = value as DataRecord
    for (const key of ['items', 'results', 'data', 'tasks', 'agents', 'predictions', 'watch_rules']) {
      if (Array.isArray(record[key])) return record[key] as T[]
    }
  }
  return []
}

export function asRecord(value: unknown): DataRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as DataRecord : {}
}

export function textValue(value: unknown, fallback = '—') {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

export function titleOf(item: unknown, fallback = '未命名') {
  const record = asRecord(item)
  return textValue(
    record.title ?? record.name ?? record.topic ?? record.label ?? record.statement ?? record.id,
    fallback
  )
}

export function formatDate(value: unknown) {
  if (typeof value !== 'string' || !value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function metricNumber(value: unknown) {
  if (typeof value === 'number') return value.toLocaleString()
  if (Array.isArray(value)) return value.length.toLocaleString()
  if (value && typeof value === 'object') return Object.keys(value).length.toLocaleString()
  if (value == null || value === '') return '0'
  return String(value)
}
