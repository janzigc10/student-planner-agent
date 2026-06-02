/// <reference lib="webworker" />

import { clientsClaim } from 'workbox-core'
import { precacheAndRoute } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

clientsClaim()
precacheAndRoute(self.__WB_MANIFEST)

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    self.skipWaiting()
  }
})

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
  const url = new URL(event.notification.data?.url ?? '/chat', self.location.origin).href
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (clients) => {
      const existing = clients.find((client): client is WindowClient => 'focus' in client)
      if (existing) {
        const target = 'navigate' in existing ? await existing.navigate(url) : existing
        return (target ?? existing).focus()
      }
      return self.clients.openWindow(url)
    }),
  )
})
