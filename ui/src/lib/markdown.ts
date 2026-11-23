import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

// 关闭原始 HTML，避免模型输出直接注入标签；表格等 GFM 语法由 markdown-it 处理。
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

export function renderMarkdown(source: string): string {
  const text = source.trim()
  if (text === '') return ''
  // DOMPurify 只放行安全标签，剥掉脚本、事件属性与 javascript: 链接。
  return DOMPurify.sanitize(markdown.render(text), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'iframe', 'object', 'embed'],
  })
}
