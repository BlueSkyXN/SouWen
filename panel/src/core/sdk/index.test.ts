import { describe, expect, it, vi } from 'vitest'
import {
  ApiMajorMismatchError,
  ContractViolationError,
  SouWenAPIError,
  SouWenClient,
  SouWenTransportError,
} from './index'

type FetchCall = [string, RequestInit]

function headers(requestId: string, init: Record<string, string> = {}): Headers {
  return new Headers({
    'X-SouWen-API-Major': '2',
    'X-SouWen-Rollout-Mode': 'target',
    'X-Request-ID': requestId,
    ...init,
  })
}

function context(requestId: string) {
  return { request_id: requestId, api_major: 2, trace_id: null }
}

function response(body: unknown, requestId: string, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: headers(requestId), ...init })
}

function probe(requestId: string, ready = true): Response {
  return response({
    status: ready ? 'ok' : 'not_ready',
    ready,
    version: '2.0.0rc2',
    rollout_mode: 'target',
    context: context(requestId),
  }, requestId, { status: ready ? 200 : 503 })
}

function requestIdOf(init: RequestInit): string {
  return new Headers(init.headers).get('X-Request-ID')!
}

describe('generated SouWenClient', () => {
  it('preflights the target API before its first business request and sends canonical headers', async () => {
    const calls: FetchCall[] = []
    const requestFetch = vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init])
      const requestId = requestIdOf(init)
      if (url.endsWith('/healthz')) return probe(requestId)
      return response({
        items: [],
        page: { limit: 10 },
        meta: {},
        context: context(requestId),
      }, requestId)
    })
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', token: 'application', fetch: requestFetch })

    await expect(client.search({ query: 'fixture', domains: ['paper'] }, { requestId: 'search-id' })).resolves.toMatchObject({
      page: { limit: 10 },
    })

    expect(calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/healthz',
      'http://localhost:8000/api/v1/search',
    ])
    const businessHeaders = new Headers(calls[1][1].headers)
    expect(businessHeaders.get('Authorization')).toBe('Bearer application')
    expect(businessHeaders.get('X-SouWen-API-Major')).toBe('2')
    expect(businessHeaders.get('X-Request-ID')).toBe('search-id')
    expect(businessHeaders.get('Content-Type')).toBe('application/json')
    expect(new Headers(calls[0][1].headers).get('X-Request-ID')).not.toBe('search-id')
    expect(calls[1][1].body).toBe(JSON.stringify({ query: 'fixture', domains: ['paper'] }))
  })

  it('uses X-SouWen-Token only when explicitly requested and accepts Probe 503 payloads', async () => {
    const calls: FetchCall[] = []
    const client = new SouWenClient({
      baseUrl: 'http://localhost:8000',
      token: 'application',
      edgeToken: 'edge',
      authChannel: 'x-souwen-token',
      fetch: vi.fn(async (url: string, init: RequestInit) => {
        calls.push([url, init])
        return probe(requestIdOf(init), false)
      }),
    })

    await expect(client.readyz({ requestId: 'ready-id' })).resolves.toMatchObject({ ready: false })
    const probeHeaders = new Headers(calls[0][1].headers)
    expect(probeHeaders.get('Authorization')).toBe('Bearer edge')
    expect(probeHeaders.get('X-SouWen-Token')).toBe('application')
  })

  it('fails closed on an API-major mismatch before issuing a business request', async () => {
    const requestFetch = vi.fn(async (_url: string, init: RequestInit) => response(
      { status: 'ok', ready: true, version: '2.0.0rc2', rollout_mode: 'target', context: context(requestIdOf(init)) },
      requestIdOf(init),
      { headers: headers(requestIdOf(init), { 'X-SouWen-API-Major': '3' }) },
    ))
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })

    await expect(client.search({ query: 'fixture', domains: ['paper'] })).rejects.toBeInstanceOf(ApiMajorMismatchError)
    expect(requestFetch).toHaveBeenCalledTimes(1)
  })

  it('fails closed when a ProbeResponse does not identify the target rollout', async () => {
    const client = new SouWenClient({
      baseUrl: 'http://localhost:8000',
      fetch: vi.fn(async (_url: string, init: RequestInit) => response({
        status: 'ready',
        ready: true,
        version: '2.0.0rc2',
        rollout_mode: 'invalid',
        context: context(requestIdOf(init)),
      }, requestIdOf(init))),
    })

    await expect(client.readyz()).rejects.toBeInstanceOf(ContractViolationError)
  })

  it('rejects whitespace-only credentials before a request can be made', () => {
    expect(() => new SouWenClient({ baseUrl: 'http://localhost:8000', token: '  ' })).toThrow(
      'token values cannot be empty',
    )
  })

  it('preserves canonical API error metadata and never retries the failed operation', async () => {
    const calls: FetchCall[] = []
    const client = new SouWenClient({
      baseUrl: 'http://localhost:8000',
      fetch: vi.fn(async (url: string, init: RequestInit) => {
        calls.push([url, init])
        const requestId = requestIdOf(init)
        if (url.endsWith('/healthz')) return probe(requestId)
        return response({
          error: { code: 'rate_limited', message: 'rate limited', retryable: true, request_id: requestId },
          context: context(requestId),
        }, requestId, {
          status: 429,
          headers: headers(requestId, { 'Retry-After': '5', 'X-RateLimit-Remaining': '0' }),
        })
      }),
    })

    await expect(client.search({ query: 'fixture', domains: ['paper'] })).rejects.toMatchObject({
      statusCode: 429,
      retryAfter: '5',
      rateLimit: { 'X-RateLimit-Remaining': '0' },
    } satisfies Partial<SouWenAPIError>)
    expect(calls).toHaveLength(2)
  })

  it('aborts at the configured timeout without retrying', async () => {
    const requestFetch = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch, timeoutMs: 1 })

    await expect(client.healthz()).rejects.toBeInstanceOf(SouWenTransportError)
    expect(requestFetch).toHaveBeenCalledTimes(1)
  })

  it('shares a default compatibility probe without letting one aborted caller poison another', async () => {
    const calls: FetchCall[] = []
    let resolveProbe: ((response: Response) => void) | undefined
    const requestFetch = vi.fn((url: string, init: RequestInit): Promise<Response> => {
      calls.push([url, init])
      if (url.endsWith('/healthz')) {
        return new Promise((resolve) => { resolveProbe = resolve })
      }
      const requestId = requestIdOf(init)
      return Promise.resolve(response({
        items: [],
        page: { limit: 10 },
        meta: {},
        context: context(requestId),
      }, requestId))
    })
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })
    const cancelled = new AbortController()
    const callerA = client.search({ query: 'cancelled', domains: ['paper'] }, {
      signal: cancelled.signal,
      timeoutMs: 1,
    })
    const callerB = client.search({ query: 'continues', domains: ['paper'] })

    cancelled.abort()
    await expect(callerA).rejects.toBeInstanceOf(SouWenTransportError)
    expect(resolveProbe).toBeDefined()
    resolveProbe!(probe(requestIdOf(calls[0][1])))

    await expect(callerB).resolves.toMatchObject({ page: { limit: 10 } })
    expect(calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/healthz',
      'http://localhost:8000/api/v1/search',
    ])
    expect(JSON.parse(calls[1][1].body as string)).toMatchObject({ query: 'continues' })
  })

  it('expires one caller compatibility wait without aborting the shared probe or another caller', async () => {
    const calls: FetchCall[] = []
    let resolveProbe: ((response: Response) => void) | undefined
    const requestFetch = vi.fn((url: string, init: RequestInit): Promise<Response> => {
      calls.push([url, init])
      if (url.endsWith('/healthz')) {
        return new Promise((resolve) => { resolveProbe = resolve })
      }
      const requestId = requestIdOf(init)
      return Promise.resolve(response({
        items: [],
        page: { limit: 10 },
        meta: {},
        context: context(requestId),
      }, requestId))
    })
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })
    const callerA = client.search({ query: 'deadline', domains: ['paper'] }, { timeoutMs: 1 })
    const callerB = client.search({ query: 'continues', domains: ['paper'] })

    await expect(callerA).rejects.toThrow('SouWen compatibility probe timed out')
    expect(resolveProbe).toBeDefined()
    resolveProbe!(probe(requestIdOf(calls[0][1])))

    await expect(callerB).resolves.toMatchObject({ page: { limit: 10 } })
    expect(calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/healthz',
      'http://localhost:8000/api/v1/search',
    ])
    expect(JSON.parse(calls[1][1].body as string)).toMatchObject({ query: 'continues' })
  })

  it('gives explicit preflight its own wait deadline and cleans its listener and timer', async () => {
    let resolveProbe: ((response: Response) => void) | undefined
    const controller = new AbortController()
    const removeListener = vi.spyOn(controller.signal, 'removeEventListener')
    const clearTimer = vi.spyOn(globalThis, 'clearTimeout')
    const requestFetch = vi.fn((_url: string, init: RequestInit): Promise<Response> => new Promise((resolve) => {
      resolveProbe = resolve
      void init
    }))
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })

    await expect(client.preflight({ signal: controller.signal, timeoutMs: 1 })).rejects.toThrow(
      'SouWen compatibility probe timed out',
    )
    expect(removeListener).toHaveBeenCalled()
    expect(clearTimer).toHaveBeenCalled()
    resolveProbe!(probe(requestIdOf(requestFetch.mock.calls[0][1])))
    await Promise.resolve()
  })

  it('rejects an already-aborted caller without starting a compatibility probe', async () => {
    const controller = new AbortController()
    controller.abort()
    const requestFetch = vi.fn(async (): Promise<Response> => new Response())
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })

    await expect(client.search({ query: 'cancelled', domains: ['paper'] }, { signal: controller.signal }))
      .rejects.toBeInstanceOf(SouWenTransportError)
    expect(requestFetch).not.toHaveBeenCalled()
  })

  it('validates per-request timeout before registering an abort listener', async () => {
    const controller = new AbortController()
    const addListener = vi.spyOn(controller.signal, 'addEventListener')
    const requestFetch = vi.fn(async (): Promise<Response> => new Response())
    const client = new SouWenClient({ baseUrl: 'http://localhost:8000', fetch: requestFetch })

    await expect(client.healthz({ signal: controller.signal, timeoutMs: 0 })).rejects.toThrow(
      'timeoutMs must be a positive finite number',
    )
    expect(addListener).not.toHaveBeenCalled()
    expect(requestFetch).not.toHaveBeenCalled()
  })
})
