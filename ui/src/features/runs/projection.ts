import {
  isTerminal,
  type CoreEvent,
  type JsonValue,
  type MessageDto,
  type RunDto,
} from '@/lib/api/contracts'

export type ToolStatus =
  'requested' | 'succeeded' | 'failed' | 'expired' | 'cancelled' | 'incomplete'
export interface ToolProjection {
  callId: string
  name: string
  mode: 'local' | 'remote'
  input: JsonValue
  status: ToolStatus
  outcome: ToolStatus | null
  messageId: number | null
  output: JsonValue
  errorCode: string | null
  errorMessage: string | null
}
export interface RunProjection {
  run: RunDto
  lastEventId: string | null
  transientText: string
  transientReasoning: string
  pendingSegments: { messageId: number; text: string; reasoning: string }[]
  completedMessageIds: number[]
  tools: ToolProjection[]
}
export function createRunProjection(run: RunDto): RunProjection {
  return {
    run,
    lastEventId: null,
    transientText: '',
    transientReasoning: '',
    pendingSegments: [],
    completedMessageIds: [],
    tools: [],
  }
}

// 投影只展示事件已经证明的事实，Run 完整状态由 HTTP 查询确认。
export function applyRunEvent(state: RunProjection, event: CoreEvent): RunProjection {
  if (event.run_id !== state.run.id) throw new Error('事件与运行不匹配。')
  // 终态 HTTP 事实已可恢复完整消息，迟到的临时增量不重复渲染。
  if (event.id === null && isTerminal(state.run)) return state
  if (
    event.id !== null &&
    state.lastEventId !== null &&
    BigInt(event.id) <= BigInt(state.lastEventId)
  )
    return state
  switch (event.type) {
    case 'message.delta':
      state.transientText += event.text
      break
    case 'reasoning.delta':
      state.transientReasoning += event.text
      break
    case 'assistant.completed':
      state.pendingSegments.push({
        messageId: event.message_id,
        text: state.transientText,
        reasoning: state.transientReasoning,
      })
      state.completedMessageIds.push(event.message_id)
      state.transientText = ''
      state.transientReasoning = ''
      break
    case 'tool.requested':
      if (state.tools.some((tool) => tool.callId === event.call_id))
        throw new Error('不同事件重复声明了工具调用。')
      state.tools.push({
        callId: event.call_id,
        name: event.tool_name,
        mode: event.execution_mode,
        input: event.input,
        status: 'requested',
        outcome: null,
        messageId: null,
        output: null,
        errorCode: null,
        errorMessage: null,
      })
      break
    case 'tool.completed':
    case 'tool.failed':
    case 'tool.expired': {
      const tool = state.tools.find((item) => item.callId === event.call_id)
      if (!tool || tool.name !== event.tool_name) throw new Error('工具事件缺少匹配的请求记录。')
      tool.messageId = event.message_id
      tool.outcome =
        event.type === 'tool.completed'
          ? 'succeeded'
          : event.type === 'tool.expired'
            ? 'expired'
            : event.error_code === 'RUN_CANCELLED'
              ? 'cancelled'
              : 'failed'
      tool.status = 'incomplete'
      if (event.type !== 'tool.completed') {
        tool.errorCode = event.error_code
        tool.errorMessage = event.error_message
      }
      break
    }
  }
  if (event.id !== null) state.lastEventId = event.id
  return state
}

export function reconcileRunMessages(state: RunProjection, messages: MessageDto[]): RunProjection {
  const related = messages.filter((message) => message.run_id === state.run.id)
  if (related.some((message) => message.session_id !== state.run.session_id))
    throw new Error('消息会话归属不一致。')
  state.pendingSegments = state.pendingSegments.filter(
    (segment) =>
      !related.some((message) => message.id === segment.messageId && message.role === 'assistant'),
  )
  for (const tool of state.tools) {
    if (tool.messageId === null) continue
    const message = related.find((item) => item.id === tool.messageId)
    if (!message) {
      tool.status = 'incomplete'
      continue
    }
    if (message.role !== 'tool' || message.tool_call_id !== tool.callId)
      throw new Error('工具结果消息关联不一致。')
    tool.output = message.content
    if (tool.outcome !== null) tool.status = tool.outcome
  }
  return state
}
