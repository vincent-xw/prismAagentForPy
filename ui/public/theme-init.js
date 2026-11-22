// 在应用模块执行前应用明确偏好，避免刷新时出现相反主题。
;(function () {
  let preference = 'system'
  try {
    const stored = localStorage.getItem('prism-ui.theme')
    if (stored === 'light' || stored === 'dark' || stored === 'system') preference = stored
  } catch {
    // 失败提示由应用展示；首次绘制遵循系统主题这一明确初始状态。
  }
  const theme =
    preference === 'system'
      ? matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : preference
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
})()
