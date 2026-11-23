// 只注册已有真实界面的模块，未来功能由各自模块接入。
export const modules = [
  { id: 'sessions', label: '会话', path: '/' },
  { id: 'workspace', label: '工作区', path: '/workspace' },
  { id: 'settings', label: '设置', path: '/settings' },
] as const
