/**
 * 文件用途：皮肤系统注册表，管理应用的主题皮肤加载、存储与查询
 *
 * 类/函数清单：
 *     RegisteredSkin（接口）
 *         - 功能：已注册皮肤的信息容器
 *         - 属性：id 皮肤唯一标识符, skinModule 皮肤模块（包含 UI 组件、路由、bootstrap）
 *
 *     registerSkin(id: string, mod: SkinModule) -> void
 *         - 功能：注册一个皮肤模块
 *         - 逻辑：第一个注册的皮肤自动成为默认皮肤；后续注册的皮肤加入注册表
 *
 *     getSkin(id: string) -> RegisteredSkin | undefined
 *         - 功能：根据 ID 查询皮肤
 *         - 输出：如果存在返回 RegisteredSkin，否则返回 undefined
 *
 *     getSkinOrDefault(id: string) -> RegisteredSkin
 *         - 功能：查询皮肤，如果不存在则回退到默认皮肤
 *         - 用途：确保始终返回有效皮肤（不会返回 undefined）
 *
 *     setActiveSkinId(id: string) -> void
 *         - 功能：设置当前活跃的皮肤 ID（运行时在内存中切换皮肤）
 *
 *     getActiveSkin() -> RegisteredSkin
 *         - 功能：获取当前活跃的皮肤
 *         - 逻辑：优先返回 activeSkinId 对应的皮肤，回退到默认皮肤
 *
 *     getDefaultSkinId() -> string
 *         - 功能：获取系统默认皮肤的 ID
 *
 *     listSkinIds() -> string[]
 *         - 功能：列出所有已注册的皮肤 ID
 *
 *     isSingleSkin() -> boolean
 *         - 功能：检查是否只有一个皮肤（用于 UI 隐藏皮肤切换控件）
 *
 *     isValidSkinId(id: string) -> boolean
 *         - 功能：验证 ID 是否对应一个有效的已注册皮肤
 *
 * 内部状态：
 *     registry Map<string, SkinModule> — 皮肤注册表
 *     defaultSkinId string — 默认皮肤 ID（第一个注册的皮肤）
 *     activeSkinId string — 当前活跃皮肤 ID
 *
 * 模块依赖：
 *     - ./types: SkinModule 类型定义
 */

import type { SkinModule } from './types'

/**
 * 已注册皮肤的信息容器
 */
export interface RegisteredSkin {
  id: string
  skinModule: SkinModule
}

/**
 * 内部皮肤注册表与当前状态
 */
const registry = new Map<string, SkinModule>()
let defaultSkinId = ''
let activeSkinId = ''

/**
 * 注册一个皮肤模块
 * 第一个注册的皮肤自动成为默认皮肤
 */
export function registerSkin(id: string, mod: SkinModule) {
  if (!defaultSkinId) defaultSkinId = id
  registry.set(id, mod)
}

/**
 * 根据 ID 查询皮肤
 * 不存在时返回 undefined
 */
export function getSkin(id: string): RegisteredSkin | undefined {
  const mod = registry.get(id)
  return mod ? { id, skinModule: mod } : undefined
}

/**
 * 查询皮肤，不存在则回退到默认皮肤
 * 始终返回有效皮肤，不会返回 undefined
 */
export function getSkinOrDefault(id: string): RegisteredSkin {
  if (registry.has(id)) return { id, skinModule: registry.get(id)! }
  return { id: defaultSkinId, skinModule: registry.get(defaultSkinId)! }
}

/**
 * 设置当前活跃的皮肤 ID
 * 仅在内存中记录，下次页面加载时会重置（需配合 localStorage 持久化）
 */
export function setActiveSkinId(id: string) {
  activeSkinId = id
}

/**
 * 获取当前活跃的皮肤
 */
export function getActiveSkin(): RegisteredSkin {
  return getSkinOrDefault(activeSkinId || defaultSkinId)
}

/**
 * 获取系统默认皮肤的 ID
 */
export function getDefaultSkinId(): string {
  return defaultSkinId
}

/**
 * 列出所有已注册的皮肤 ID
 */
export function listSkinIds(): string[] {
  return [...registry.keys()]
}

/**
 * 检查是否仅有一个皮肤
 * 用于 UI 隐藏皮肤切换控件
 */
export function isSingleSkin(): boolean {
  return registry.size === 1
}

/**
 * 验证皮肤 ID 是否有效（已注册）
 */
export function isValidSkinId(id: string): boolean {
  return registry.has(id)
}
