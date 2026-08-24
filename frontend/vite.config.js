import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 静态构建后由 FastAPI 挂载在 /app 下;dev 时把 /api 代理到 T430。
// VITE_TAURI=1 打桌面包:base 用相对路径(Tauri 资源协议根目录);否则网页版挂 /app/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_TAURI ? './' : '/app/',
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8200', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8200', changeOrigin: true },
    },
  },
})
