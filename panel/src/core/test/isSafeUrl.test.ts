/**
 * 文件用途：isSafeUrl 安全 URL 校验函数单元测试
 *
 * 被测对象：``panel/src/core/hooks/useFetchPage.ts`` 中导出的 ``isSafeUrl``。
 * 该函数用于决定面板是否把抓取结果中的 ``final_url`` 渲染为可点击链接，是
 * 防御反射型 XSS / file:// 任意文件访问的最后一道防线。
 *
 * 当前实现仅按协议白名单校验：``/^https?:\/\//i.test(url)``。本测试套件
 * 同时覆盖：
 *
 *     describe('isSafeUrl - protocol whitelist')
 *         - 合法 http(s) URL 返回 true
 *         - file:// / javascript: / data: 等危险协议返回 false
 *         - 空串、相对 URL 返回 false
 *
 *     describe('isSafeUrl - private network addresses (current behavior)')
 *         - RFC1918 + 127.0.0.1 等私网地址在当前实现下仍返回 true
 *         - 这些用例当作回归基线：若未来加入 SSRF 防护，需要主动改这些断言
 */

import { describe, it, expect } from 'vitest'
import { isSafeUrl } from '../hooks/useFetchPage'

describe('isSafeUrl - protocol whitelist', () => {
  it('accepts https URLs', () => {
    expect(isSafeUrl('https://example.com')).toBe(true)
    expect(isSafeUrl('https://example.com/path?q=1#frag')).toBe(true)
  })

  it('accepts http URLs', () => {
    expect(isSafeUrl('http://example.com')).toBe(true)
  })

  it('is case-insensitive on the scheme', () => {
    expect(isSafeUrl('HTTPS://example.com')).toBe(true)
    expect(isSafeUrl('Http://example.com')).toBe(true)
  })

  it('rejects file:// URLs', () => {
    expect(isSafeUrl('file:///etc/passwd')).toBe(false)
    expect(isSafeUrl('file://localhost/etc/hosts')).toBe(false)
  })

  it('rejects javascript: URLs (XSS vector)', () => {
    expect(isSafeUrl('javascript:alert(1)')).toBe(false)
    expect(isSafeUrl('JAVASCRIPT:alert(1)')).toBe(false)
  })

  it('rejects data: URLs', () => {
    expect(isSafeUrl('data:text/html,<script>alert(1)</script>')).toBe(false)
  })

  it('rejects other dangerous schemes', () => {
    expect(isSafeUrl('vbscript:msgbox(1)')).toBe(false)
    expect(isSafeUrl('chrome://settings')).toBe(false)
    expect(isSafeUrl('about:blank')).toBe(false)
  })

  it('rejects empty / whitespace strings', () => {
    expect(isSafeUrl('')).toBe(false)
    expect(isSafeUrl('   ')).toBe(false)
  })

  it('rejects relative URLs (no scheme)', () => {
    expect(isSafeUrl('/api/v1/fetch')).toBe(false)
    expect(isSafeUrl('example.com')).toBe(false)
    expect(isSafeUrl('//example.com')).toBe(false)
  })
})

describe('isSafeUrl - private network addresses (current behavior)', () => {
  /*
   * 当前 isSafeUrl 只做协议白名单，不做主机名/IP 检查。这些用例锁定该
   * 现状，若日后引入 SSRF / private-IP 防护，需要把这些断言改为 false。
   */
  it('still returns true for RFC1918 / loopback hosts (no SSRF guard yet)', () => {
    expect(isSafeUrl('http://192.168.1.1')).toBe(true)
    expect(isSafeUrl('http://10.0.0.1')).toBe(true)
    expect(isSafeUrl('http://172.16.0.1')).toBe(true)
    expect(isSafeUrl('http://127.0.0.1')).toBe(true)
    expect(isSafeUrl('http://localhost')).toBe(true)
  })
})
