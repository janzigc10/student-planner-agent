/// <reference lib="webworker" />

import { clientsClaim } from 'workbox-core'
import { precacheAndRoute } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

clientsClaim()
precacheAndRoute(self.__WB_MANIFEST)

self.addEventListener('push', (event) => {
  const payload = event.data?.json() as { title?: string; body?: string } | undefined
  const title = payload?.title ?? '学习规划助手'
  const body = payload?.body ?? '你有新的学习提醒'
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/pwa.svg',
      badge: '/pwa.svg',
      data: { url: '/chat' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url ?? '/chat'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((client) => 'focus' in client)
      if (existing) {
        return existing.focus()
      }
      return self.clients.openWindow(url)
    }),
  )
})
