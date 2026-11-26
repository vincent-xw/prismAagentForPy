import type { MessageDto, RunDto, SessionDto } from '@/lib/api/contracts'

// 完整 DTO 夹具只用于测试；生产请求不补造字段。
export const stamp = '2026-11-22T00:00:00Z'
export function sessionDto(overrides: Partial<SessionDto> = {}): SessionDto {
  return {
    id: 's1',
    title: null,
    workspace_id: null,
    created_at: stamp,
    updated_at: stamp,
    ...overrides,
  }
}
export function runDto(overrides: Partial<RunDto> = {}): RunDto {
  return {
    id: 'r1',
    session_id: 's1',
    status: 'running',
    workspace_id: null,
    input: '你好',
    prompt_ref: 'default',
    model: 'test-model',
    step_count: 0,
    output: null,
    error_code: null,
    error_message: null,
    cancel_requested_at: null,
    created_at: stamp,
    started_at: stamp,
    finished_at: null,
    ...overrides,
  }
}
export function messageDto(overrides: Partial<MessageDto> = {}): MessageDto {
  return {
    id: 1,
    session_id: 's1',
    run_id: 'r1',
    role: 'user',
    kind: 'text',
    content: '你好',
    reasoning: null,
    tool_call_id: null,
    created_at: stamp,
    ...overrides,
  }
}
