import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { NotificationsPage } from './NotificationsPage'

const SUBSCRIPTION_JSON = {
  endpoint: 'https://fcm.googleapis.com/fcm/send/fake-token',
  keys: {
    p256dh: 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8p8REfWPU=',
    auth: 'tBHItJI5svbpC7-BnWW_IA==',
  },
}

function installNotificationGlobals() {
  const notificationMock = {
    permission: 'granted' as NotificationPermission,
    requestPermission: vi.fn().mockResolvedValue('granted' as NotificationPermission),
  }
  vi.stubGlobal('Notification', notificationMock as unknown as typeof Notification)
  vi.stubGlobal('PushManager', function PushManager() {} as unknown as typeof PushManager)
  return notificationMock
}

function installServiceWorkerMocks(getSubscriptionValue: PushSubscription | null) {
  const subscription = getSubscriptionValue
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(subscription),
    subscribe: vi.fn(),
  }
  const registration = { pushManager }
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      ready: Promise.resolve(registration),
    },
  })
  return { registration, pushManager }
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    window.localStorage.setItem('student-planner-token', 'stored-token')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('shows a resync hint when this device already has a push subscription but the server does not', async () => {
    installNotificationGlobals()
    const localSubscription = {
      toJSON: () => SUBSCRIPTION_JSON,
      unsubscribe: vi.fn(),
    } as unknown as PushSubscription
    installServiceWorkerMocks(localSubscription)
    vi.spyOn(api, 'getPushStatus').mockResolvedValue({
      subscribed: false,
      vapid_configured: true,
    })

    render(<NotificationsPage />)

    expect(await screen.findByText('本机订阅：已存在')).toBeInTheDocument()
    expect(screen.getByText('服务器订阅：未保存')).toBeInTheDocument()
    expect(screen.getByText('检测到本机已有通知订阅，但服务器还没保存。点“开启推送通知”可重新同步。')).toBeInTheDocument()
  })

  it('reuses an existing local subscription and syncs it back to the server', async () => {
    const notificationMock = installNotificationGlobals()
    const localSubscription = {
      toJSON: () => SUBSCRIPTION_JSON,
      unsubscribe: vi.fn(),
    } as unknown as PushSubscription
    const { pushManager } = installServiceWorkerMocks(localSubscription)
    vi.spyOn(api, 'getPushStatus').mockResolvedValue({
      subscribed: false,
      vapid_configured: true,
    })
    const subscribeSpy = vi.spyOn(api, 'subscribePush').mockResolvedValue({ status: 'subscribed' })
    const getVapidKeySpy = vi.spyOn(api, 'getVapidKey').mockResolvedValue({ public_key: 'unused' })

    render(<NotificationsPage />)

    await screen.findByText('本机订阅：已存在')
    await userEvent.click(screen.getByRole('button', { name: '开启推送通知' }))

    await waitFor(() => {
      expect(subscribeSpy).toHaveBeenCalledWith(SUBSCRIPTION_JSON)
    })
    expect(notificationMock.requestPermission).toHaveBeenCalled()
    expect(pushManager.subscribe).not.toHaveBeenCalled()
    expect(getVapidKeySpy).not.toHaveBeenCalled()
    expect(await screen.findByText('已把当前设备的通知订阅重新同步到服务器。')).toBeInTheDocument()
    expect(screen.getByText('服务器订阅：已保存')).toBeInTheDocument()
  })
})
