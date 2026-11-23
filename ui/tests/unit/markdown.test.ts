import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'

import MarkdownContent from '@/components/markdown/MarkdownContent.vue'
import { renderMarkdown } from '@/lib/markdown'

test('渲染 GFM 表格为 table 结构', () => {
  const html = renderMarkdown('| 名称 | 数量 |\n| --- | --- |\n| 苹果 | 2 |')

  expect(html).toContain('<table>')
  expect(html).toContain('<th>名称</th>')
  expect(html).toContain('<td>苹果</td>')
})

test('渲染常见 Markdown 语法', () => {
  const html = renderMarkdown('**粗体** 与 `code`\n\n- 一\n- 二')

  expect(html).toContain('<strong>粗体</strong>')
  expect(html).toContain('<code>code</code>')
  expect(html).toContain('<li>一</li>')
})

test('剥离原始 HTML 与 javascript 链接', () => {
  const html = renderMarkdown('<script>alert(1)</script>\n\n[bad](javascript:alert(1))')

  expect(html).not.toContain('<script')
  expect(html).not.toContain('href="javascript:')
  expect(html).not.toContain('<a')
})

test('空内容不产生额外结构', () => {
  expect(renderMarkdown('')).toBe('')
})

test('组件把表格渲染进 DOM', () => {
  const wrapper = mount(MarkdownContent, {
    props: { source: '| a | b |\n| --- | --- |\n| 1 | 2 |' },
  })

  expect(wrapper.find('table').exists()).toBe(true)
  expect(wrapper.findAll('td')).toHaveLength(2)
})
