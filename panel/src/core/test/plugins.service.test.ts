/**
 * 文件用途：plugins service 路径与请求 body 的单元测试。
 *
 * 重点验证：
 *   - URL 段使用 encodeURIComponent，避免插件名包含 ` ` 等字符时崩坏
 *   - install/uninstall 请求体使用 `package` 字段（与后端 InstallRequest 对齐）
 *   - 列表/详情/health 走 GET，启用/禁用/install/uninstall/reload 走 POST
 */

import { describe, expect, it, vi } from 'vitest'
import { pluginsMethods } from '../services/plugins'

function makeContext() {
  const request = vi.fn().mockResolvedValue({ ok: true })
  const headers = vi.fn().mockReturnValue({ Authorization: 'Bearer x' })
  return {
    ctx: { request, headers } as unknown as Parameters<
      typeof pluginsMethods.listPlugins
    >[0],
    request,
  }
}

describe('plugins service', () => {
  it('lists plugins via GET /api/v1/admin/plugins', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.listPlugins.call(ctx as never)
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
    const opts = request.mock.calls[0]?.[1]
    expect(opts?.method).toBeUndefined() // GET
  })

  it('encodes plugin names containing reserved chars', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.getPlugin.call(ctx as never, 'web 2 pdf')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/web%202%20pdf',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('hits /health endpoint via GET', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.getPluginHealth.call(ctx as never, 'demo')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/demo/health',
      expect.objectContaining({ headers: expect.any(Object) }),
    )
  })

  it('enables a plugin via POST without body', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.enablePlugin.call(ctx as never, 'demo')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/demo/enable',
      expect.objectContaining({ method: 'POST' }),
    )
    const opts = request.mock.calls[0]?.[1]
    expect(opts?.body).toBeUndefined()
  })

  it('disables a plugin via POST without body', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.disablePlugin.call(ctx as never, 'demo')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/demo/disable',
      expect.objectContaining({ method: 'POST' }),
    )
    const opts = request.mock.calls[0]?.[1]
    expect(opts?.body).toBeUndefined()
  })

  it('installs by sending {package} in body', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.installPlugin.call(ctx as never, 'superweb2pdf')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/install',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ package: 'superweb2pdf' }),
      }),
    )
  })

  it('uninstalls by sending {package} in body', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.uninstallPlugin.call(ctx as never, 'superweb2pdf')
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/uninstall',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ package: 'superweb2pdf' }),
      }),
    )
  })

  it('reloads via POST', async () => {
    const { ctx, request } = makeContext()
    await pluginsMethods.reloadPlugins.call(ctx as never)
    expect(request).toHaveBeenCalledWith(
      '/api/v1/admin/plugins/reload',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
