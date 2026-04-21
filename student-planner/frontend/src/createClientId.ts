let fallbackCounter = 0

export function createClientId(): string {
  const randomUUID = globalThis.crypto?.randomUUID
  if (typeof randomUUID === 'function') {
    return randomUUID.call(globalThis.crypto)
  }

  fallbackCounter += 1
  return `client-${Date.now().toString(36)}-${fallbackCounter.toString(36)}`
}
