import { describe, expect, it } from 'vitest'
import { LOGIN_SERVER_URL_EXAMPLE } from '../lib/serverConnection'

describe('server connection UI constants', () => {
  it('keeps the login server URL example stable for placeholders', () => {
    expect(LOGIN_SERVER_URL_EXAMPLE).toBe('http://localhost:8000')
  })
})
