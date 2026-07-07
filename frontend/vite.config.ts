import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), '')
  
  // 从环境变量获取后端地址，用于开发环境代理
  // 如果未设置，使用 IPv4 loopback，避免 localhost 被系统代理/IPv6 解析绕走
  const API_URL = env.VITE_API_URL || 'http://127.0.0.1:8000'
  const WS_URL = env.VITE_WS_URL || 'ws://127.0.0.1:8000'
  const BRIDGE_RUNTIME_URL = env.VITE_BRIDGE_RUNTIME_URL || 'http://127.0.0.1:8080'
  
  // 从环境变量获取版本信息（构建时注入）
  const VERSION = env.VERSION || 'dev'
  const GIT_TAG = env.GIT_TAG || ''
  const GITHUB_REPO_URL = env.GITHUB_REPO_URL || 'https://github.com/WrBug/PolyHermes'
  
  return {
    plugins: [react()],
    define: {
      // 注入版本信息到全局变量
      'window.__VERSION__': JSON.stringify({
        version: VERSION,
        gitTag: GIT_TAG,
        githubRepoUrl: GITHUB_REPO_URL
      })
    },
    server: {
      host: '::',
      port: 3000,
      proxy: {
        '/api': {
          target: API_URL,
          changeOrigin: true
        },
        '/ws': {
          target: WS_URL,
          ws: true,
          changeOrigin: true
        },
        '/bridge-runtime': {
          target: BRIDGE_RUNTIME_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/bridge-runtime/, '')
        }
      }
    }
  }
})
