import { useState } from 'react'

import { api } from '../api/client'
import { BellIcon } from '../components/icons'

function urlBase64ToUint8Array(value: string) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)))
}

export function NotificationsPage() {
  const [status, setStatus] = useState(Notification.permission)

  async function subscribe() {
    const permission = await Notification.requestPermission()
    setStatus(permission)
    if (permission !== 'granted') return
    const registration = await navigator.serviceWorker.ready
    const { public_key } = await api.getVapidKey()
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    })
    await api.subscribePush(subscription.toJSON())
  }

  async function unsubscribe() {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    await subscription?.unsubscribe()
    await api.unsubscribePush()
    setStatus(Notification.permission)
  }

  return (
    <main className="page">
      <section className="notification-settings">
        <h2 className="notification-settings__title">
          <BellIcon className="icon" />
          <span>通知设置</span>
        </h2>
        <p>当前状态：{status}</p>
        {status === 'denied' ? <p className="status-inline status-inline--warning">请在浏览器设置中重新开启通知权限。</p> : null}
        <button className="primary-button" type="button" onClick={() => void subscribe()}>
          开启推送通知
        </button>
        <button type="button" onClick={() => void unsubscribe()}>
          关闭推送通知
        </button>
      </section>
    </main>
  )
}
