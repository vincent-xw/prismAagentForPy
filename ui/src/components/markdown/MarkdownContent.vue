<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{ source: string }>()
const html = computed(() => renderMarkdown(props.source))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- 内容由 renderMarkdown 经 DOMPurify 清洗后输出 -->
  <div class="markdown-body break-words text-sm leading-8" v-html="html" />
</template>

<style scoped>
.markdown-body :deep(p) {
  margin: 0.5rem 0;
}
.markdown-body :deep(p:first-child) {
  margin-top: 0;
}
.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 1.25rem 0 0.5rem;
  font-weight: 600;
  line-height: 1.4;
}
.markdown-body :deep(h1) {
  font-size: 1.25rem;
}
.markdown-body :deep(h2) {
  font-size: 1.125rem;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.4rem;
}
.markdown-body :deep(ul) {
  list-style: disc;
}
.markdown-body :deep(ol) {
  list-style: decimal;
}
.markdown-body :deep(li) {
  margin: 0.15rem 0;
}
.markdown-body :deep(a) {
  color: var(--color-primary, #2563eb);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.markdown-body :deep(code) {
  border-radius: 0.3rem;
  background: var(--color-secondary, rgba(0, 0, 0, 0.06));
  padding: 0.1rem 0.3rem;
  font-size: 0.85em;
}
.markdown-body :deep(pre) {
  margin: 0.75rem 0;
  overflow-x: auto;
  border-radius: 0.75rem;
  background: var(--color-secondary, rgba(0, 0, 0, 0.06));
  padding: 0.75rem 1rem;
}
.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 0.85em;
}
.markdown-body :deep(blockquote) {
  margin: 0.75rem 0;
  border-left: 3px solid var(--color-border, rgba(0, 0, 0, 0.12));
  padding-left: 0.9rem;
  color: var(--color-muted-foreground, rgba(0, 0, 0, 0.6));
}
.markdown-body :deep(table) {
  display: block;
  width: max-content;
  max-width: 100%;
  margin: 0.75rem 0;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: 0.875em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-border, rgba(0, 0, 0, 0.12));
  padding: 0.4rem 0.75rem;
  text-align: left;
  vertical-align: top;
}
.markdown-body :deep(th) {
  background: var(--color-secondary, rgba(0, 0, 0, 0.06));
  font-weight: 600;
  white-space: nowrap;
}
.markdown-body :deep(hr) {
  margin: 1rem 0;
  border: 0;
  border-top: 1px solid var(--color-border, rgba(0, 0, 0, 0.12));
}
</style>
