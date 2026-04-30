/**
 * 文件用途：Wayback API 路径单元测试。
 */

import { describe, expect, it, vi } from 'vitest'
import { waybackMethods } from '../services/wayback'

describe('wayback service', () => {
  it('uses the admin route for Save Page Now writes', async () => {
    const request = vi.fn().mockResolvedValue({ success: true })
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ 'Content-Type': 'application/json' }),
    }

    await waybackMethods.waybackSave.call(ctx as never, 'https://example.com', 60)

    expect(request).toHaveBeenCalledWith('/api/v1/admin/wayback/save', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ url: 'https://example.com', timeout: 60 }),
    }))
  })
})
