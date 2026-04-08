import { describe, it, expect } from 'vitest'
import { AppError, formatError } from '../lib/errors'

describe('AppError', () => {
  describe('fromResponse', () => {
    it('creates auth error for 401', () => {
      const err = AppError.fromResponse(401, 'Unauthorized')
      expect(err.status).toBe(401)
      expect(err.isAuth).toBe(true)
      expect(err.isNetwork).toBe(false)
      expect(err.message).toBe('Unauthorized')
    })

    it('creates auth error for 403', () => {
      const err = AppError.fromResponse(403, '')
      expect(err.isAuth).toBe(true)
      expect(err.message).toBe('HTTP 403')
    })

    it('creates non-auth error for 500', () => {
      const err = AppError.fromResponse(500, 'Server Error')
      expect(err.isAuth).toBe(false)
      expect(err.status).toBe(500)
    })

    it('uses default message when body is empty', () => {
      const err = AppError.fromResponse(404, '')
      expect(err.message).toBe('HTTP 404')
    })
  })

  describe('network', () => {
    it('wraps Error cause', () => {
      const err = AppError.network(new Error('fetch failed'))
      expect(err.isNetwork).toBe(true)
      expect(err.isAuth).toBe(false)
      expect(err.status).toBe(0)
      expect(err.message).toBe('fetch failed')
    })

    it('uses default message for non-Error cause', () => {
      const err = AppError.network('something')
      expect(err.message).toBe('网络连接失败')
    })

    it('uses default message for undefined', () => {
      const err = AppError.network()
      expect(err.message).toBe('网络连接失败')
    })
  })
})

describe('formatError', () => {
  it('formats AppError', () => {
    expect(formatError(new AppError('test error'))).toBe('test error')
  })

  it('formats generic Error', () => {
    expect(formatError(new Error('oops'))).toBe('oops')
  })

  it('returns default for non-Error', () => {
    expect(formatError('string')).toBe('未知错误')
    expect(formatError(null)).toBe('未知错误')
    expect(formatError(42)).toBe('未知错误')
  })
})
