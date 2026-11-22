import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

// 合并组件变体与调用方样式，处理互斥的 Tailwind 类。
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Vue 宏将可选 props 表现为显式 undefined；向 Reka 转发时省略这些键，
// 遵循 exactOptionalPropertyTypes，不为缺失 prop 填值或关闭严格检查。
export function definedProps<T extends object>(
  props: T,
): { [K in keyof T]: Exclude<T[K], undefined> } {
  return Object.fromEntries(Object.entries(props).filter(([, value]) => value !== undefined)) as {
    [K in keyof T]: Exclude<T[K], undefined>
  }
}
