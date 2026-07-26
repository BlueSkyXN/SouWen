import { useMemo } from 'react'
import { SouWenClient } from '@core/sdk'
import { assertBaseUrlAllowed } from '@core/services/_base'
import { useAuthStore } from '@core/stores/authStore'

/**
 * Create the generated data-plane client from the authenticated connection.
 *
 * The Panel deliberately has no second data transport: Search, LLM Search,
 * Fetch and Provider calls must all go through this generated client.
 */
export function createSouWenClient(): SouWenClient {
  const { baseUrl, token } = useAuthStore.getState()
  assertBaseUrlAllowed(baseUrl)
  return new SouWenClient({ baseUrl, token: token || undefined })
}

/** Keep one generated client for the currently authenticated React view. */
export function useSouWenClient(): SouWenClient {
  const baseUrl = useAuthStore((state) => state.baseUrl)
  const token = useAuthStore((state) => state.token)
  return useMemo(() => {
    assertBaseUrlAllowed(baseUrl)
    return new SouWenClient({ baseUrl, token: token || undefined })
  }, [baseUrl, token])
}
