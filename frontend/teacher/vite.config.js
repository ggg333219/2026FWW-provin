import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],

  // ECharts is already shipped in the local node_modules tree, but Vite's
  // dependency optimizer can choke on its package layout in this workspace.
  // Excluding it keeps dev startup on the simpler native ESM path.
  optimizeDeps: {
    exclude: ['echarts'],
  },

  build: {
    // 将 echarts 拆分为独立 chunk，避免 1.1 MB 的大包警告
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts')) {
            return 'echarts'
          }
          if (id.includes('node_modules/katex')) {
            return 'katex'
          }
          if (id.includes('node_modules/vue') || id.includes('node_modules/pinia') || id.includes('node_modules/vue-router')) {
            return 'vendor'
          }
        },
      },
    },
    // 增大 chunk 大小警告阈值（echarts 即使拆分也有 ~900 kB）
    chunkSizeWarningLimit: 1200,
  },
})
