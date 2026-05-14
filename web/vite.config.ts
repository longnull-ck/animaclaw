import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:3210',
      '/ws': { target: 'ws://localhost:3210', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    // 代码分割策略
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
        },
      },
    },
    // 生产优化
    minify: 'esbuild',
    sourcemap: false,
    // 超过 500KB 才报警告
    chunkSizeWarningLimit: 500,
    // 目标：现代浏览器
    target: 'es2020',
  },
  // 性能优化
  optimizeDeps: {
    include: ['react', 'react-dom'],
  },
})
