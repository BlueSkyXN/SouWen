/**
 * 文件用途：Bilibili 直连 API 占位文件。
 *
 * 现状（2025-）：原 ApiService 中没有 Bilibili 专用方法 —
 * 视频搜索通过聚合搜索 `/api/v1/search/web?engine=bilibili` 走 searchWeb，
 * 视频详情/用户搜索/文章搜索如需直连后端，请在此补充并通过 mixin 注入。
 *
 * 保留本文件是为了与 V1 重构计划的目录结构对齐，方便后续按域扩展。
 */

import type { ApiServiceBase } from './_base'

// 当前无方法。新增方法时请同步声明 BilibiliApi 接口字段，并将方法对象合并到此处导出的
// bilibiliMethods 对象中，由 services/index.ts 通过 Object.assign 注入到原型。
export type BilibiliApi = Record<string, never>

export const bilibiliMethods: Record<string, (this: ApiServiceBase, ...args: never[]) => Promise<unknown>> = {}
