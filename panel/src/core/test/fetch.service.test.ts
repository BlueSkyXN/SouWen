/**
 * 文件用途：fetch service 请求体序列化回归测试。
 */

import { describe, expect, it, vi } from 'vitest'
import { fetchMethods } from '../services/fetch'

describe('fetch service', () => {
  it('sends advanced fetch options including providers, strategy, and zero values', async () => {
    const request = vi.fn().mockResolvedValue({ total: 0, total_ok: 0, total_failed: 0, results: [] })
    const ctx = {
      request,
      headers: vi.fn().mockReturnValue({ 'Content-Type': 'application/json' }),
    }

    await fetchMethods.fetch.call(
      ctx as never,
      ['https://example.com'],
      'builtin',
      12,
      undefined,
      {
        providers: ['builtin', 'jina_reader'],
        strategy: 'fanout',
        selector: 'article',
        startIndex: 0,
        maxLength: 0,
        respectRobotsTxt: true,
      },
    )

    expect(request).toHaveBeenCalledWith('/api/v1/fetch', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        urls: ['https://example.com'],
        provider: 'builtin',
        timeout: 12,
        providers: ['builtin', 'jina_reader'],
        strategy: 'fanout',
        selector: 'article',
        start_index: 0,
        max_length: 0,
        respect_robots_txt: true,
      }),
      timeoutMs: 32_000,
    }))
  })
})
