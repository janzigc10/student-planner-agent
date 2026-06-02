import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { BellIcon } from '../components/icons'

function urlBase64ToUint8Array(value: string) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)))
}

export function NotificationsPage() {
  const notificationsSupported =
    typeof window !== 'undefined' &&
    'Notification' in window &&
    'serviceWorker' in navigator &&
    'PushManager' in window

  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(
    notificationsSupported ? Notification.permission : 'unsupported',
  )
  const [browserSubscribed, setBrowserSubscribed] = useState<boolean | null>(null)
  const [serverSubscribed, setServerSubscribed] = useState<boolean | null>(null)
  const [vapidConfigured, setVapidConfigured] = useState<boolean | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isBusy, setIsBusy] = useState(false)

  useEffect(() => {
    if (!notificationsSupported) {
      setBrowserSubscribed(false)
      setServerSubscribed(false)
      setVapidConfigured(false)
      return
    }

    async function loadStatus() {
      try {
        const registration = await navigator.serviceWorker.ready
        const subscription = await registration.pushManager.getSubscription()
        const serverStatus = await api.getPushStatus()
        setPermission(Notification.permission)
        setBrowserSubscribed(Boolean(subscription))
        setServerSubscribed(serverStatus.subscribed)
        setVapidConfigured(serverStatus.vapid_configured)
        setError(null)
        if (subscription && !serverStatus.subscribed) {
          setMessage('检测到本机已有通知订阅，但服务器还没保存。点“开启推送通知”可重新同步。')
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : '通知状态读取失败')
      }
    }

    void loadStatus()
  }, [notificationsSupported])

  async function subscribe() {
    if (!notificationsSupported) {
      setError('当前浏览器不支持推送通知。')
      return
    }

    setIsBusy(true)
    setError(null)
    setMessage(null)
    try {
      const nextPermission = await Notification.requestPermission()
      setPermission(nextPermission)
      if (nextPermission !== 'granted') {
        setError('通知权限未授予，请在系统和 Chrome 设置中开启通知。')
        return
      }
      const registration = await navigator.serviceWorker.ready
      let subscription = await registration.pushManager.getSubscription()
      let reusedExistingSubscription = true
      if (!subscription) {
        reusedExistingSubscription = false
        const { public_key } = await api.getVapidKey()
        if (!public_key) {
          throw new Error('服务器尚未配置推送密钥，请稍后重试。')
        }
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(public_key),
        })
      }
      await api.subscribePush(subscription.toJSON())
      setBrowserSubscribed(true)
      setServerSubscribed(true)
      setVapidConfigured(true)
      setMessage(reusedExistingSubscription ? '已把当前设备的通知订阅重新同步到服务器。' : '推送通知已开启。')
    } catch (subscribeError) {
      setError(subscribeError instanceof Error ? subscribeError.message : '开启推送通知失败')
    } finally {
      setIsBusy(false)
    }
  }

  async function unsubscribe() {
    if (!notificationsSupported) {
      setError('当前浏览器不支持推送通知。')
      return
    }

    setIsBusy(true)
    setError(null)
    setMessage(null)
    try {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      await subscription?.unsubscribe()
      await api.unsubscribePush()
      setPermission(Notification.permission)
      setBrowserSubscribed(false)
      setServerSubscribed(false)
      setMessage('推送通知已关闭。')
    } catch (unsubscribeError) {
      setError(unsubscribeError instanceof Error ? unsubscribeError.message : '关闭推送通知失败')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <main className="page">
      <section className="notification-settings">
        <h2 className="notification-settings__title">
          <BellIcon className="icon" />
          <span>通知设置</span>
        </h2>
        <p>通知权限：{permission}</p>
        <p>本机订阅：{browserSubscribed === null ? '读取中…' : browserSubscribed ? '已存在' : '未检测到'}</p>
        <p>服务器订阅：{serverSubscribed === null ? '读取中…' : serverSubscribed ? '已保存' : '未保存'}</p>
        {vapidConfigured === false ? (
          <p className="status-inline status-inline--warning">服务器尚未配置推送密钥，暂时无法开启推送。</p>
        ) : null}
        {permission === 'denied' ? <p className="status-inline status-inline--warning">请在浏览器设置中重新开启通知权限。</p> : null}
        {message ? <p className="status-inline">{message}</p> : null}
        {error ? <p className="status-inline status-inline--warning" role="alert">{error}</p> : null}
        <button className="primary-button" type="button" onClick={() => void subscribe()} disabled={isBusy}>
          开启推送通知
        </button>
        <button type="button" onClick={() => void unsubscribe()} disabled={isBusy}>
          关闭推送通知
        </button>
      </section>
    </main>
  )
}
