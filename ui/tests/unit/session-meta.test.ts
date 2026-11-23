import { mount } from '@vue/test-utils'
import { expect, test, vi } from 'vitest'

import SessionMeta from '@/features/sessions/SessionMeta.vue'
import type { SessionDto, WorkspaceDto } from '@/lib/api/contracts'

const session: SessionDto = {
  id: 'sess-123',
  title: 'demo',
  workspace_id: 'w1',
  created_at: '2026-11-23T00:00:00Z',
  updated_at: '2026-11-23T00:00:00Z',
}
const workspaces: WorkspaceDto[] = [
  {
    id: 'w1',
    root_path: '/Users/me/project-a',
    label: 'project-a',
    is_active: true,
    index_status: 'ready',
    index_error: null,
    file_count: 3,
    indexed_at: null,
  },
]

test('展示会话绑定的工作区名称', () => {
  const wrapper = mount(SessionMeta, { props: { session, workspaces } })
  expect(wrapper.text()).toContain('project-a')
})

test('点击复制按钮复制会话 ID', async () => {
  const writeText = vi.fn(async () => {})
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const wrapper = mount(SessionMeta, { props: { session, workspaces } })

  await wrapper.get('button[aria-label="复制会话 ID"]').trigger('click')

  expect(writeText).toHaveBeenCalledWith('sess-123')
  expect(wrapper.text()).toContain('已复制')
})
