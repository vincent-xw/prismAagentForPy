import { expect, test } from 'vitest'

import { compactNotice } from '@/features/sessions/compaction'

test('压缩结果提示包含前后 token', () => {
  expect(compactNotice({ compacted: true, tokens_before: 9000, tokens_after: 1200 })).toContain(
    '9000 → 1200',
  )
})

test('无可压缩内容提示', () => {
  expect(compactNotice({ compacted: false, reason: 'nothing_to_compact' })).toContain('没有可压缩')
})
