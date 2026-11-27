import { expect, test } from 'vitest'

import { contextUsageSchema } from '@/lib/api/contracts'
import { formatTokens, usageLabel, usageTone } from '@/features/sessions/contextUsage'

const usage = {
  context_window: 65536,
  max_output_tokens: 8192,
  budget_tokens: 55296,
  used_tokens: 12000,
  percent: 21.7,
  threshold: 0.85,
  needs_compaction: false,
  compactable: true,
  last_compaction: null,
}

test('formatTokens 缩写', () => {
  expect(formatTokens(950)).toBe('950')
  expect(formatTokens(1200)).toBe('1.2k')
  expect(formatTokens(55296)).toBe('55.3k')
})

test('usageLabel 展示百分比与预算', () => {
  expect(usageLabel(usage)).toBe('上下文 21.7% · 12k/55.3k')
  expect(usageLabel(null)).toBe('上下文 —')
})

test('usageTone 阈值判断', () => {
  expect(usageTone(usage)).toBe('ok')
  expect(usageTone({ ...usage, percent: 70 })).toBe('warn')
  expect(usageTone({ ...usage, percent: 90, needs_compaction: true })).toBe('danger')
})

test('contextUsageSchema 拒绝缺字段', () => {
  expect(contextUsageSchema.parse(usage).used_tokens).toBe(12000)
  const missing: Record<string, unknown> = { ...usage }
  delete missing.used_tokens
  expect(() => contextUsageSchema.parse(missing)).toThrow()
})
