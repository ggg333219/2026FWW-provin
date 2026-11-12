import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    // 既有单测继续跑 node；公共组件测试用文件级
    // `// @vitest-environment jsdom` 单独切到 jsdom，避免影响历史用例。
    environment: 'node',
    include: ['src/{utils,stores,services,components/voice,components/common}/**/*.test.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      include: ['src/utils/markdownRenderer.js']
    }
  }
})
