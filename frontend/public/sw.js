// Service Worker - 仅用于 PWA 安装，不做离线缓存（数据依赖服务器）
const CACHE_NAME = 'daily-system-v1'

self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

// 不拦截网络请求，让所有请求正常走网络
self.addEventListener('fetch', (event) => {
  // pass-through
})
