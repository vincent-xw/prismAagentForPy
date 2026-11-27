import type { CompactResultDto } from '@/lib/api/contracts'

export function compactNotice(result: CompactResultDto): string {
  if (!result.compacted) {
    return '当前会话没有可压缩的内容'
  }
  return `上下文已压缩：${result.tokens_before ?? 0} → ${result.tokens_after ?? 0} tokens`
}
