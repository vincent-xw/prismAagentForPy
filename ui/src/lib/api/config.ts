// 只允许同源路径，避免配置把凭据发送到任意 URL。
export function parseApiBasePath(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !/^\/[A-Za-z0-9/_-]+$/.test(value) ||
    value.startsWith('//') ||
    value.endsWith('/')
  ) {
    throw new Error('VITE_API_BASE_PATH 必须是明确的同源 API 路径，例如 /api/v1。')
  }
  return value
}
