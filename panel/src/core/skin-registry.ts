import type { SkinModule } from './types'

export interface RegisteredSkin {
  id: string
  skinModule: SkinModule
}

const registry = new Map<string, SkinModule>()
let defaultSkinId = ''
let activeSkinId = ''

export function registerSkin(id: string, mod: SkinModule) {
  if (!defaultSkinId) defaultSkinId = id
  registry.set(id, mod)
}

export function getSkin(id: string): RegisteredSkin | undefined {
  const mod = registry.get(id)
  return mod ? { id, skinModule: mod } : undefined
}

export function getSkinOrDefault(id: string): RegisteredSkin {
  if (registry.has(id)) return { id, skinModule: registry.get(id)! }
  return { id: defaultSkinId, skinModule: registry.get(defaultSkinId)! }
}

export function setActiveSkinId(id: string) {
  activeSkinId = id
}

export function getActiveSkin(): RegisteredSkin {
  return getSkinOrDefault(activeSkinId || defaultSkinId)
}

export function getDefaultSkinId(): string {
  return defaultSkinId
}

export function listSkinIds(): string[] {
  return [...registry.keys()]
}

export function isSingleSkin(): boolean {
  return registry.size === 1
}

export function isValidSkinId(id: string): boolean {
  return registry.has(id)
}
