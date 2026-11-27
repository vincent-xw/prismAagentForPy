import { expect, test } from 'vitest'

import { trajectorySchema } from '@/lib/api/contracts'

test('轨迹契约解析 legacy Step 与 compaction', () => {
  const parsed = trajectorySchema.parse({
    turns: [
      {
        run: {
          id: 'r1',
          status: 'succeeded',
          input_text: 'hi',
          created_at: '2026-11-27T00:00:00Z',
          finished_at: '2026-11-27T00:00:02Z',
        },
        steps: [
          {
            index: 0,
            model: 'm1',
            usage: null,
            duration_ms: 1200,
            finish_reason: null,
            assistant_message_id: null,
            tools: [],
            legacy: true,
          },
        ],
        compactions: [
          { id: 'c1', tokens_before: 9000, tokens_after: 1200, created_at: '2026-11-27T00:00:01Z' },
        ],
      },
    ],
  })

  expect(parsed.turns[0]?.steps[0]?.legacy).toBe(true)
})
