import js from '@eslint/js'
import { defineConfig, globalIgnores } from 'eslint/config'
import prettier from 'eslint-config-prettier'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

// 为 TypeScript 与 Vue 单文件组件使用同一组基础检查规则。
export default defineConfig(
  globalIgnores([
    'dist/**',
    'node_modules/**',
    '.vite/**',
    'test-results/**',
    'playwright-report/**',
  ]),
  js.configs.recommended,
  tseslint.configs.recommended,
  vue.configs['flat/recommended'],
  {
    files: ['src/**/*.{ts,vue}', 'public/*.js'],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    files: ['src/components/ui/**/*.vue'],
    // 基础控件沿用官方名称；可选 prop 保持省略语义，不强制填入默认值。
    rules: { 'vue/multi-word-component-names': 'off', 'vue/require-default-prop': 'off' },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    files: ['*.config.{js,ts}'],
    languageOptions: {
      globals: globals.node,
    },
  },
  // 格式统一交给 Prettier，避免与 ESLint 的排版规则冲突。
  prettier,
)
