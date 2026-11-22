import { computed, ref, watch } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'
const key = 'prism-ui.theme'

// 每个应用只装配一次主题服务；事件监听随应用生命周期释放。
export function useTheme() {
  const preference = ref<ThemePreference>('system')
  const storageError = ref<string | null>(null)
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const systemDark = ref(media.matches)
  try {
    const stored = localStorage.getItem(key)
    if (stored === 'light' || stored === 'dark' || stored === 'system') preference.value = stored
    else if (stored !== null) storageError.value = '已保存的外观偏好无效，请重新选择。'
  } catch {
    storageError.value = '无法读取外观偏好，本次选择仅在当前页面生效。'
  }
  const resolvedTheme = computed(() =>
    preference.value === 'system' ? (systemDark.value ? 'dark' : 'light') : preference.value,
  )
  const apply = watch(
    resolvedTheme,
    (value) => {
      document.documentElement.dataset.theme = value
      document.documentElement.style.colorScheme = value
    },
    { immediate: true },
  )
  const onChange = () => {
    systemDark.value = media.matches
  }
  media.addEventListener('change', onChange)
  function setPreference(value: ThemePreference) {
    preference.value = value
    try {
      localStorage.setItem(key, value)
      storageError.value = null
    } catch {
      storageError.value = '无法保存外观偏好，本次选择仅在当前页面生效。'
    }
  }
  return {
    preference,
    resolvedTheme,
    storageError,
    setPreference,
    dispose() {
      apply()
      media.removeEventListener('change', onChange)
    },
  }
}
