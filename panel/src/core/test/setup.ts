/**
 * 文件用途：测试环境初始化，配置 Vitest + React Testing Library 的全局 setup
 *
 * 初始化内容：
 *     - 导入 @testing-library/jest-dom/vitest，为 expect() 添加 DOM 匹配器
 *       （如 toBeInTheDocument()、toHaveClass() 等）
 */

import '@testing-library/jest-dom/vitest'

type StorageName = 'localStorage' | 'sessionStorage'

function createMemoryStorage(): Storage {
  const data = new Map<string, string>()

  return {
    get length() {
      return data.size
    },
    clear() {
      data.clear()
    },
    getItem(key: string) {
      return data.has(key) ? data.get(key)! : null
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null
    },
    removeItem(key: string) {
      data.delete(key)
    },
    setItem(key: string, value: string) {
      data.set(key, value)
    },
  }
}

function ensureStorage(name: StorageName) {
  const current = globalThis[name]
  if (typeof current?.clear === 'function' && typeof current?.getItem === 'function') return

  const storage = createMemoryStorage()
  Object.defineProperty(globalThis, name, { value: storage, configurable: true })
  Object.defineProperty(window, name, { value: storage, configurable: true })
}

ensureStorage('localStorage')
ensureStorage('sessionStorage')
