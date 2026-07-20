/**
 * 文件用途：ApiServiceBase 登录验证行为测试。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiServiceBase } from '../services/_base'
import { AppError } from '../lib/errors'

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('ApiServiceBase.verifyAuth', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('verifies credentials against /api/v1/whoami and returns role data', async () => {
    const whoami = {
      role: 'admin',
      features: { config_write: true },
      guest_enabled: false,
      user_password_set: true,
      admin_password_set: true,
      admin_open: false,
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(whoami))
    const api = new ApiServiceBase()

    await expect(api.verifyAuth('http://localhost:8000', 'admin-pw')).resolves.toEqual(whoami)
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/whoami',
      expect.objectContaining({
        headers: { Authorization: 'Bearer admin-pw' },
      }),
    )
  })

  it('does not auto-login with an empty token when admin password is configured', async () => {
    const whoami = {
      role: 'user',
      features: { config_write: false },
      guest_enabled: false,
      user_password_set: false,
      admin_password_set: true,
      admin_open: false,
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(whoami))
    const api = new ApiServiceBase()

    await expect(api.verifyAuth('http://localhost:8000', '')).rejects.toMatchObject({
      status: 401,
      isAuth: true,
    } satisfies Partial<AppError>)
  })

  it('does not send bearer tokens to unallowlisted third-party base URLs', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({
        role: 'admin',
        features: {},
        guest_enabled: false,
        user_password_set: true,
        admin_password_set: true,
        admin_open: false,
      }),
    )
    const api = new ApiServiceBase()

    await expect(api.verifyAuth('https://example.com', 'admin-pw')).rejects.toThrow(
      /VITE_ALLOWED_API_HOSTS/,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
