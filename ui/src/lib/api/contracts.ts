import { z } from 'zod'

// DTO 严格保留 Core 的字段与 null 语义；未知扩展字段可以忽略，必需字段不得补造。
const id = z.string().min(1)
const date = z.iso.datetime({ offset: true })
const jsonObject = z.record(z.string(), z.json())
export const sessionSchema = z.object({
  id,
  title: z.string().nullable(),
  workspace_id: id.nullable(),
  created_at: date,
  updated_at: date,
})
export const runSchema = z.object({
  id,
  session_id: id,
  status: z.enum([
    'queued',
    'running',
    'waiting_for_tool',
    'waiting_for_approval',
    'succeeded',
    'failed',
    'cancelled',
  ]),
  workspace_id: id.nullable(),
  input: z.string(),
  prompt_ref: z.string(),
  model: z.string(),
  step_count: z.number().int().nonnegative(),
  output: z.string().nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  cancel_requested_at: date.nullable(),
  created_at: date,
  started_at: date.nullable(),
  finished_at: date.nullable(),
})
export const messageSchema = z.object({
  id: z.number().int().positive(),
  session_id: id,
  run_id: id,
  role: z.enum(['user', 'assistant', 'tool']),
  content: z.json(),
  reasoning: z.string().nullable(),
  tool_call_id: z.string().nullable(),
  created_at: date,
})
export const toolSchema = z.object({
  name: id,
  description: z.string(),
  execution_mode: z.enum(['local', 'remote']),
  input_schema: jsonObject,
  output_schema: jsonObject.nullable(),
})
export const sessionsSchema = z.object({ items: z.array(sessionSchema) })
export const messagesSchema = z.object({ items: z.array(messageSchema) })
export const toolsSchema = z.object({ items: z.array(toolSchema) })
export const toolCallSchema = z.object({
  id,
  run_id: id,
  tool_name: id,
  status: z.enum([
    'pending',
    'running',
    'awaiting_approval',
    'succeeded',
    'failed',
    'expired',
    'cancelled',
  ]),
  output: z.json(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  expires_at: date.nullable(),
})
export const workspaceSchema = z.object({
  id,
  root_path: z.string(),
  label: z.string().nullable(),
  is_active: z.boolean(),
  index_status: z.enum(['idle', 'indexing', 'ready', 'failed']),
  index_error: z.string().nullable(),
  file_count: z.number().int().nonnegative(),
  indexed_at: date.nullable(),
})
export const workspacePickSchema = z.object({ path: z.string() })
export const workspaceListSchema = z.object({
  items: z.array(workspaceSchema),
  active_id: id.nullable(),
})
export const treeResponseSchema = z.object({
  items: z.array(
    z.object({
      name: z.string(),
      type: z.enum(['file', 'dir']),
      size: z.number().int().nullable().optional(),
      modified_at: z.number().nullable().optional(),
    }),
  ),
})
export const fileResponseSchema = z.object({
  path: z.string(),
  content: z.string(),
  truncated: z.boolean(),
  size: z.number().int().nonnegative(),
})
export const searchResponseSchema = z.object({
  items: z.array(z.object({ path: z.string(), snippet: z.string() })),
})
export const approvalPreviewSchema = z.object({
  kind: z.enum(['file', 'generic']),
  path: z.string(),
  input_preview: z.string().nullable(),
  mode: z.string(),
  bytes: z.number().int().nonnegative(),
  exists: z.boolean(),
  diff: z.string().nullable(),
  truncated: z.boolean(),
})
export const approvalResponseSchema = z.object({
  call: toolCallSchema,
  run: runSchema,
})
export const healthSchema = z.object({
  status: z.literal('ok'),
  service: z.string(),
  version: z.string(),
  environment: z.string(),
})
export const errorSchema = z.object({
  error: z.object({ code: id, message: z.string(), request_id: id, details: jsonObject }),
})
export type SessionDto = z.infer<typeof sessionSchema>
export type RunDto = z.infer<typeof runSchema>
export type MessageDto = z.infer<typeof messageSchema>
export type ToolDto = z.infer<typeof toolSchema>
export type HealthDto = z.infer<typeof healthSchema>
export type JsonValue = z.infer<ReturnType<typeof z.json>>

const base = { run_id: id }
const toolResult = { ...base, call_id: id, tool_name: id, message_id: z.number().int().positive() }
const toolFailure = { ...toolResult, error_code: id, error_message: z.string() }
const eventSchema = z.discriminatedUnion('type', [
  z.object({
    ...base,
    type: z.literal('run.queued'),
    prompt_ref: z.string(),
    metadata: jsonObject,
  }),
  z.object({ ...base, type: z.literal('run.started') }),
  z.object({
    ...base,
    type: z.literal('assistant.completed'),
    message_id: z.number().int().positive(),
    tool_call_ids: z.array(id),
  }),
  z.object({
    ...base,
    type: z.literal('tool.requested'),
    call_id: id,
    tool_name: id,
    execution_mode: z.enum(['local', 'remote']),
    // 需审批工具的正文不入事件，payload 只带 path/mode/bytes 摘要。
    input: z.json().optional(),
    path: z.string().optional(),
    mode: z.string().optional(),
    bytes: z.number().int().nonnegative().optional(),
    input_digest: id,
  }),
  z.object({ ...toolResult, type: z.literal('tool.completed') }),
  z.object({ ...toolFailure, type: z.literal('tool.failed') }),
  z.object({ ...toolFailure, type: z.literal('tool.expired') }),
  z.object({ ...base, type: z.literal('run.waiting_for_tool'), call_ids: z.array(id) }),
  z.object({ ...base, type: z.literal('run.waiting_for_approval'), call_ids: z.array(id) }),
  z.object({
    ...base,
    type: z.literal('tool.approval_required'),
    call_id: id,
    tool_name: id,
    kind: z.enum(['file', 'generic']).optional(),
    path: z.string().optional(),
    mode: z.string().optional(),
    bytes: z.number().int().nonnegative().optional(),
    input_preview: z.string().optional(),
  }),
  z.object({ ...base, type: z.literal('tool.approved'), call_id: id }),
  z.object({
    ...base,
    type: z.literal('tool.rejected'),
    call_id: id,
    reason: z.string().optional(),
  }),
  z.object({ ...base, type: z.literal('run.requeued'), call_ids: z.array(id) }),
  z.object({
    ...base,
    type: z.literal('context.trimmed'),
    trimmed_count: z.number().int().nonnegative(),
    trimmed_tokens: z.number().int().nonnegative(),
  }),
  z.object({ ...base, type: z.literal('run.succeeded'), message_id: z.number().int().positive() }),
  z.object({ ...base, type: z.literal('run.failed'), error_code: id, error_message: z.string() }),
  z.object({ ...base, type: z.literal('run.cancelled') }),
  z.object({ ...base, type: z.literal('message.delta'), text: z.string() }),
  z.object({ ...base, type: z.literal('reasoning.delta'), text: z.string() }),
])
export type CoreEvent = z.infer<typeof eventSchema> & { id: string | null }

// 整数字符串不转成 JS number，保留大游标精度。
export function parseCoreEvent(name: string, eventId: string | null, value: unknown): CoreEvent {
  const event = eventSchema.parse(value)
  if (event.type !== name) throw new Error('SSE 类型与事件正文不一致。')
  const temporary = event.type === 'message.delta' || event.type === 'reasoning.delta'
  if (temporary ? eventId !== null : eventId === null || !/^\d+$/.test(eventId))
    throw new Error('SSE 事件游标不合法。')
  return { ...event, id: eventId }
}
export function isTerminal(run: RunDto): boolean {
  return run.status === 'succeeded' || run.status === 'failed' || run.status === 'cancelled'
}

export type ToolCallDto = z.infer<typeof toolCallSchema>
export type WorkspaceDto = z.infer<typeof workspaceSchema>
export type TreeEntryDto = z.infer<typeof treeResponseSchema>['items'][number]
export type FileDto = z.infer<typeof fileResponseSchema>
export type SearchHitDto = z.infer<typeof searchResponseSchema>['items'][number]
export type ApprovalPreviewDto = z.infer<typeof approvalPreviewSchema>

export const mcpServerSchema = z.object({
  id: z.string(),
  name: z.string(),
  transport: z.enum(['stdio', 'http']),
  command: z.string().nullable(),
  args: z.array(z.string()),
  url: z.string().nullable(),
  enabled: z.boolean(),
  status: z.string(),
  last_error: z.string().nullable(),
  tool_count: z.number().int().nonnegative(),
  env_keys: z.array(z.string()),
  header_keys: z.array(z.string()),
  env: z.record(z.string(), z.string()),
  headers: z.record(z.string(), z.string()),
})
export const mcpServersSchema = z.array(mcpServerSchema)
export const mcpToolSchema = z.object({
  name: z.string(),
  description: z.string(),
  input_schema: z.record(z.string(), z.unknown()),
})
export const mcpToolsSchema = z.object({
  server_id: z.string(),
  tools: z.array(mcpToolSchema),
})
export type McpServerDto = z.infer<typeof mcpServerSchema>
export type McpToolDto = z.infer<typeof mcpToolSchema>
export interface McpServerPayload {
  name: string
  transport: 'stdio' | 'http'
  command: string | null
  args: string[]
  env: Record<string, string>
  url: string | null
  headers: Record<string, string>
  enabled: boolean
}
