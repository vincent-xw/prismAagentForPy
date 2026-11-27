import type { ContextUsageDto } from '@/lib/api/contracts'

/** 把 token 数格式化为 1.2k / 29k 这类短文本。 */
export function formatTokens(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '0'
  if (value < 1000) return String(Math.round(value))
  const k = value / 1000
  return k >= 100 ? `${Math.round(k)}k` : `${k.toFixed(1).replace(/\.0$/, '')}k`
}

export function usageLabel(usage: ContextUsageDto | null): string {
  if (usage === null) return '上下文 —'
  return `上下文 ${usage.percent.toFixed(1).replace(/\.0$/, '')}% · ${formatTokens(
    usage.used_tokens,
  )}/${formatTokens(usage.budget_tokens)}`
}

export function usageTone(usage: ContextUsageDto | null): 'ok' | 'warn' | 'danger' {
  if (usage === null) return 'ok'
  if (usage.needs_compaction) return 'danger'
  return usage.percent >= usage.threshold * 100 * 0.7 ? 'warn' : 'ok'
}
