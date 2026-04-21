import { afterEach, describe, expect, it, vi } from 'vitest'

import { createClientId } from './createClientId'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createClientId', () => {
  it('uses crypto.randomUUID when available', () => {
    const randomUUID = vi.fn(() => 'uuid-1')
    vi.stubGlobal('crypto', { randomUUID } as unknown as Crypto)

    expect(createClientId()).toBe('uuid-1')
    expect(randomUUID).toHaveBeenCalledOnce()
  })

  it('falls back to a local id when crypto.randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', {} as unknown as Crypto)

    expect(createClientId()).toMatch(/^client-/)
  })
})
