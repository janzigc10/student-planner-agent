import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from './client'

describe('api client errors', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('uses backend json detail for upload errors', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: '课表图片最多支持 3 张。' }), {
        status: 400,
        statusText: 'Bad Request',
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(api.uploadSchedule([new File(['img'], '1.png', { type: 'image/png' })])).rejects.toEqual(
      new ApiError('课表图片最多支持 3 张。', 400),
    )
  })
})
