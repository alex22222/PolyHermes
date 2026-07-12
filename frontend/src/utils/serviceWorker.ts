/**
 * 注册 Service Worker，支持 PWA 离线访问。
 * 仅在生产构建且浏览器支持时注册。
 */
export function registerServiceWorker() {
  if (import.meta.env.DEV) {
    return
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          console.debug('Service Worker 注册成功:', registration.scope)
        })
        .catch((error) => {
          console.error('Service Worker 注册失败:', error)
        })
    })
  }
}
