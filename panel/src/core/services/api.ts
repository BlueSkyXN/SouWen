/**
 * 公开入口：原 panel/src/core/services/api.ts 已按域拆分到同目录的
 * _base / search / fetch / sources / admin / warp / http-backend /
 * source-config / youtube / wayback / proxy / bilibili 文件中，并在 ./index.ts
 * 完成 ApiService 的装配与单例 `api` 的导出。
 *
 * 本文件作为便捷别名，让 `import { api } from '@core/services/api'` 与
 * `import { api } from '@core/services'` 两条路径等价。
 */

export * from './index'
export { default } from './index'
