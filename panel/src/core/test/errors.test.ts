/**
 * 文件用途：错误处理单元测试，验证 AppError 创建、分类、格式化
 *
 * 测试套件清单：
 *
 *     describe('AppError')
 *
 *         describe('fromResponse')
 *             - 测试从 HTTP 响应创建错误实例
 *
 *             it('creates auth error for 401')
 *                 - 验证：401 状态码自动标记为认证错误（isAuth=true）
 *
 *             it('creates permission error for 403')
 *                 - 验证：403 状态码不标记为认证错误
 *                 - 验证：空响应体时用 HTTP 状态文本作为消息
 *
 *             it('creates non-auth error for 500')
 *                 - 验证：500 等其他状态码不标记为认证错误（isAuth=false）
 *
 *             it('uses default message when body is empty')
 *                 - 验证：响应体为空时，使用 "HTTP {status}" 格式作为消息
 *
 *         describe('network')
 *             - 测试网络错误创建
 *
 *             it('wraps Error cause')
 *                 - 验证：Error 对象作为原因时，提取其消息
 *                 - 验证：isNetwork=true，status=0
 *
 *             it('uses default message for non-Error cause')
 *                 - 验证：非 Error 对象时，用 i18n 默认网络错误文本
 *
 *             it('uses default message for undefined')
 *                 - 验证：未传入 cause 时，同样使用 i18n 默认文本
 *
 *     describe('formatError')
 *         - 测试错误格式化为用户可读字符串
 *
 *         it('formats AppError')
 *             - 验证：AppError 直接返回其 message
 *
 *         it('formats generic Error')
 *             - 验证：标准 Error 返回其 message
 *
 *         it('returns default for non-Error')
 *             - 验证：其他类型值（字符串、数字、null）返回 i18n 默认未知错误文本
 */

import { describe, it, expect } from 'vitest'
import { AppError, formatError } from '../lib/errors'

describe('AppError', () => {
  describe('fromResponse', () => {
    /**
     * 测试：401 响应创建认证错误
     */
    it('creates auth error for 401', () => {
      const err = AppError.fromResponse(401, 'Unauthorized')
      expect(err.status).toBe(401)
      expect(err.isAuth).toBe(true)
      expect(err.isNetwork).toBe(false)
      expect(err.message).toBe('Unauthorized')
    })

    /**
     * 测试：403 响应创建权限错误，不触发认证登出
     */
    it('creates permission error for 403', () => {
      const err = AppError.fromResponse(403, '')
      expect(err.isAuth).toBe(false)
      expect(err.message).toBe('HTTP 403')
    })

    /**
     * 测试：500 等非认证错误
     */
    it('creates non-auth error for 500', () => {
      const err = AppError.fromResponse(500, 'Server Error')
      expect(err.isAuth).toBe(false)
      expect(err.status).toBe(500)
    })

    /**
     * 测试：空响应体使用默认消息
     */
    it('uses default message when body is empty', () => {
      const err = AppError.fromResponse(404, '')
      expect(err.message).toBe('HTTP 404')
    })
  })

  describe('network', () => {
    /**
     * 测试：包装 Error 原因
     */
    it('wraps Error cause', () => {
      const err = AppError.network(new Error('fetch failed'))
      expect(err.isNetwork).toBe(true)
      expect(err.isAuth).toBe(false)
      expect(err.status).toBe(0)
      expect(err.message).toBe('fetch failed')
    })

    /**
     * 测试：非 Error 原因使用默认消息
     */
    it('uses default message for non-Error cause', () => {
      const err = AppError.network('something')
      expect(err.message).toBe('网络连接失败')
    })

    /**
     * 测试：无原因时使用默认消息
     */
    it('uses default message for undefined', () => {
      const err = AppError.network()
      expect(err.message).toBe('网络连接失败')
    })
  })
})

describe('formatError', () => {
  /**
   * 测试：格式化 AppError
   */
  it('formats AppError', () => {
    expect(formatError(new AppError('test error'))).toBe('test error')
  })

  /**
   * 测试：格式化标准 Error
   */
  it('formats generic Error', () => {
    expect(formatError(new Error('oops'))).toBe('oops')
  })

  /**
   * 测试：非 Error 值返回默认文本
   */
  it('returns default for non-Error', () => {
    expect(formatError('string')).toBe('未知错误')
    expect(formatError(null)).toBe('未知错误')
    expect(formatError(42)).toBe('未知错误')
  })
})
