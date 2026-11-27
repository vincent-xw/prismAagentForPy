import { expect, test, vi } from 'vitest'

import type { CoreClient } from '@/lib/api/client'
import { createModelsController } from '@/features/models/models'

const profile = {
  id: 'p1',
  name: 'primary',
  base_url: 'https://api.example.com/v1',
  model: 'model-a',
  api_key_env: 'OPENAI_API_KEY',
  context_window: 128000,
  max_output_tokens: 4096,
  is_active: false,
  has_key: false,
}

test('加载档案列表', async () => {
  const client = {
    listModelProfiles: vi.fn().mockResolvedValue([profile]),
  } as unknown as CoreClient
  const controller = createModelsController({ client })

  await controller.load()

  expect(controller.state.profiles).toHaveLength(1)
})

test('切换档案后刷新并提示下次生效', async () => {
  const list = vi
    .fn()
    .mockResolvedValueOnce([profile])
    .mockResolvedValueOnce([{ ...profile, is_active: true }])
  const client = {
    listModelProfiles: list,
    activateModelProfile: vi.fn().mockResolvedValue({ ...profile, is_active: true }),
  } as unknown as CoreClient
  const controller = createModelsController({ client })
  await controller.load()

  await controller.activate(profile)

  expect(controller.state.profiles[0]?.is_active).toBe(true)
  expect(controller.state.notice).toContain('下一次请求生效')
})
