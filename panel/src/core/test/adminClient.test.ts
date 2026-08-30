import { afterEach, describe, expect, it, vi } from 'vitest'
import { adminClient } from '../services/admin-client'
import { useAuthStore } from '../stores/authStore'

describe('Calm Precision admin client', () => {
  afterEach(() => {
    useAuthStore.getState().logout()
    vi.restoreAllMocks()
  })

  it('uses the admin doctor route with the authenticated control-plane header', async () => {
    useAuthStore.getState().setAuth('http://localhost:8000', 'test-token', '2.0.0rc6')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', sources: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await adminClient.getDoctor()

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/admin/doctor',
      expect.objectContaining({
        headers: {
          Authorization: 'Bearer test-token',
          'Content-Type': 'application/json',
        },
      }),
    )
  })
})
