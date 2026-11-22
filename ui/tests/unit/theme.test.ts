import { afterEach, expect, test, vi } from 'vitest'
import { useTheme } from '@/app/theme/useTheme'

afterEach(() => localStorage.clear())

test('显式主题不跟随系统变化，系统偏好随媒体事件变化', () => {
  const media = new EventTarget()
  Object.assign(media, { matches: false })
  vi.stubGlobal('matchMedia', () => media)
  const theme = useTheme()
  theme.setPreference('dark')
  expect(theme.resolvedTheme.value).toBe('dark')
  media.dispatchEvent(new Event('change'))
  expect(theme.resolvedTheme.value).toBe('dark')
  theme.setPreference('system')
  expect(theme.resolvedTheme.value).toBe('light')
  Object.assign(media, { matches: true })
  media.dispatchEvent(new Event('change'))
  expect(theme.resolvedTheme.value).toBe('dark')
  theme.dispose()
})

test('无法保存偏好时仍允许本页切换并反馈存储错误', () => {
  vi.stubGlobal('matchMedia', () => Object.assign(new EventTarget(), { matches: false }))
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  const theme = useTheme()
  theme.setPreference('dark')
  expect(theme.storageError.value).not.toBeNull()
  expect(theme.resolvedTheme.value).toBe('dark')
  theme.dispose()
})
