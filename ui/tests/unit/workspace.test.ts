import { expect, test, vi } from 'vitest'

import { createWorkspaceController } from '@/features/workspace/workspace'
import type { CoreClient } from '@/lib/api/client'

const workspace = {
  id: 'w1',
  root_path: '/tmp/proj',
  label: 'proj',
  name: null,
  permission_mode: 'workspace_write',
  is_active: true,
  index_status: 'indexing' as const,
  index_error: null,
  file_count: 0,
  indexed_at: null,
}

function fakeClient() {
  return {
    listWorkspaces: vi.fn(async () => ({ items: [workspace], active_id: 'w1' })),
    getWorkspace: vi.fn(async () => workspace),
    activateWorkspace: vi.fn(async () => ({ ...workspace, id: 'w2' })),
    createWorkspace: vi.fn(async () => workspace),
    updateWorkspace: vi.fn(async () => workspace),
    pickWorkspace: vi.fn(async () => ({ path: '/tmp/proj' })),
    reindexWorkspace: vi.fn(async () => workspace),
    getTree: vi.fn(async () => ({ items: [] })),
    getFile: vi.fn(async () => ({ path: 'a.md', content: 'hello', truncated: false, size: 5 })),
    searchWorkspace: vi.fn(async () => ({ items: [] })),
  }
}

test('索引中会继续轮询直到 ready', async () => {
  const client = fakeClient()
  const controller = createWorkspaceController({ client: client as unknown as CoreClient })
  await controller.refreshActive()
  expect(client.getWorkspace).toHaveBeenCalledTimes(1)
  await controller.pollOnce()
  expect(client.getWorkspace).toHaveBeenCalledTimes(2)
})

test('切换工作区后清空文件与搜索状态', async () => {
  const client = fakeClient()
  const controller = createWorkspaceController({ client: client as unknown as CoreClient })
  await controller.refreshActive()
  await controller.openFile('a.md')
  expect(controller.state.file).not.toBeNull()
  await controller.activate('w2')
  expect(controller.state.file).toBeNull()
  expect(controller.state.entries).toEqual([])
  expect(controller.state.searchResults).toEqual([])
})

test('打开目录会加载条目', async () => {
  const client = fakeClient()
  const controller = createWorkspaceController({ client: client as unknown as CoreClient })
  await controller.refreshActive()
  await controller.openDirectory('docs')
  expect(client.getTree).toHaveBeenCalledWith('w1', 'docs')
  expect(controller.state.currentPath).toBe('docs')
})

test('full_access 需要二次确认，取消则不调用 PATCH', async () => {
  const client = fakeClient()
  const controller = createWorkspaceController({ client: client as unknown as CoreClient })
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)

  const changed = await controller.setPermission('w1', 'full_access')

  expect(changed).toBe(false)
  expect(confirmSpy).toHaveBeenCalledTimes(1)
  expect(client.updateWorkspace).not.toHaveBeenCalled()

  confirmSpy.mockReturnValue(true)
  const accepted = await controller.setPermission('w1', 'full_access')
  expect(accepted).toBe(true)
  expect(client.updateWorkspace).toHaveBeenCalledWith('w1', { permission_mode: 'full_access' })
  confirmSpy.mockRestore()
})
