/**
 * 兼容性 shim：原 panel/src/core/services/api.ts 已按域拆分到同目录的
 * _base / search / fetch / sources / admin / warp / http-backend /
 * source-config / youtube / wayback / proxy / bilibili 文件中，并在 ./index.ts
 * 完成 ApiService 的装配与单例 `api` 的导出。
 *
 * 本文件仅做透传以保持 `import { api } from '@core/services/api'` 等旧路径有效，
 * 新代码请直接 `import { api } from '@core/services'`。
 */

export * from './index'
export { default } from './index'
