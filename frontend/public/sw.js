const CACHE_NAME = 'polyhermes-cache-v1'
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/mobile-portfolio'
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS)
    }).catch(() => {})
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    })
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // API / WebSocket 不缓存
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) {
    return
  }

  // 静态资源：优先缓存
  if (request.method === 'GET') {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) {
          return cached
        }
        return fetch(request).then((response) => {
          if (
            response &&
            response.status === 200 &&
            response.type === 'basic'
          ) {
            const responseClone = response.clone()
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone)
            })
          }
          return response
        }).catch(() => {
          // 离线时返回缓存的首页
          if (request.mode === 'navigate') {
            return caches.match('/index.html')
          }
        })
      })
    )
  }
})
