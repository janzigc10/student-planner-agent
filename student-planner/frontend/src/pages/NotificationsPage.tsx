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
  const permissionLabel = permission === 'unsupported' ? '不支持' : permission
  const browserLabel = browserSubscribed === null ? '读取中…' : browserSubscribed ? '已存在' : '未检测到'
  const serverLabel = serverSubscribed === null ? '读取中…' : serverSubscribed ? '已保存' : '未保存'
  const chainReady = permission === 'granted' && browserSubscribed === true && serverSubscribed === true

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
    <main className="page notifications-page">
      <section className={`notification-health ${chainReady ? 'notification-health--ready' : ''}`} aria-label="推送健康度">
        <header>
          <strong>推送健康度</strong>
          <span className={`notification-state ${chainReady ? 'notification-state--ready' : ''}`}>
            {chainReady ? '已就绪' : '待处理'}
          </span>
        </header>
        <div className="notification-health__meter" aria-hidden="true">
          <span />
        </div>
        <div className="notification-health__chips">
          <p className={permission === 'granted' ? 'is-ready' : ''}>
            <strong>权限</strong>
            <span>{permissionLabel}</span>
          </p>
          <p className={browserSubscribed ? 'is-ready' : ''}>
            <strong>设备</strong>
            <span>{browserLabel}</span>
          </p>
          <p className={serverSubscribed ? 'is-ready' : ''}>
            <strong>服务器</strong>
            <span>{serverLabel}</span>
          </p>
        </div>
      </section>
      <details className="settings-accordion notification-accordion">
        <summary>
          <BellIcon className="icon" />
          <div>
            <h2>推送链路</h2>
            <p>{chainReady ? '浏览器、设备和服务器都已就绪' : '点开查看三段状态'}</p>
          </div>
        </summary>
        <div className="settings-accordion__body notification-panel__body">
          <p className="notification-note">任意一段断开，任务提醒都可能只停在系统里。</p>
          <div className="status-grid notification-chain">
            <p className={permission === 'granted' ? 'is-ready' : ''}>
              <span>01 浏览器权限</span>
              <strong>通知权限：{permissionLabel}</strong>
            </p>
            <p className={browserSubscribed ? 'is-ready' : ''}>
              <span>02 当前设备</span>
              <strong>本机订阅：{browserLabel}</strong>
            </p>
            <p className={serverSubscribed ? 'is-ready' : ''}>
              <span>03 服务器记录</span>
              <strong>服务器订阅：{serverLabel}</strong>
            </p>
          </div>
        </div>
      </details>
      {vapidConfigured === false ? (
        <p className="status-inline status-inline--warning">服务器尚未配置推送密钥，暂时无法开启推送。</p>
      ) : null}
      {permission === 'denied' ? <p className="status-inline status-inline--warning">请在浏览器设置中重新开启通知权限。</p> : null}
      {message ? <p className="status-inline">{message}</p> : null}
      {error ? <p className="status-inline status-inline--warning" role="alert">{error}</p> : null}
      <div className="notification-actions">
        <button className="primary-button" type="button" onClick={() => void subscribe()} disabled={isBusy}>
          开启推送通知
        </button>
        <button type="button" onClick={() => void unsubscribe()} disabled={isBusy}>
          关闭推送通知
        </button>
      </div>
    </main>
  )
}
