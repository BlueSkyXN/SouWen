/**
 * 文件用途：admin service 读端点路由回归测试。
 */

import { describe, expect, it, vi } from 'vitest'
import { adminMethods } from '../services/admin'

describe('admin service', () => {
  it('reads doctor status through the user-readable endpoint', async () => {
    const request = vi.fn().mockResolvedValue({ total: 0, ok: 0, sources: [] })
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ Authorization: 'Bearer user-pw' }),
    }

    await adminMethods.getDoctor.call(ctx as never)

    expect(request).toHaveBeenCalledWith('/api/v1/doctor', {
      headers: { Authorization: 'Bearer user-pw' },
    })
  })
})
