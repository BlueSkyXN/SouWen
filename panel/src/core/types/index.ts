/**
 * 文件用途：核心类型聚合入口。
 *
 * 内容范围：
 *   - 通过 `export * from './api'` 透传所有 API 响应/搜索类型，保持 `import ... from '@core/types'` 的旧路径兼容
 *   - 仅在本文件内定义 UI / 皮肤系统相关类型（Theme、Toast、SearchCategory、SkinConfig 等）
 *
 * 拆分原因（V1 重构）：
 *   - 将 API 类型集中到 ./api.ts，便于按域定位/演进
 *   - 与 services 层（按域拆分的 search/fetch/youtube/... ）形成对应关系
 *
 * 模块依赖：
 *     - React: 用于 React.ComponentType 类型
 */

// 透传所有 API 响应类型（HealthResponse / SearchResponse / WarpStatus / ...）
export * from './api'

/* ===== UI Types ===== */

/**
 * 应用主题：明亮或深色
 */
export type Theme = 'light' | 'dark'

/**
 * 皮肤配色方案 ID
 * 每个皮肤可定义多个方案（如 nebula/aurora/obsidian），用户可切换
 */
export type VisualTheme = string

/**
 * 通知/Toast 类型
 */
export type ToastType = 'success' | 'error' | 'info'

/**
 * 通知对象
 */
export interface Toast {
  id: string
  type: ToastType
  message: string
}

/**
 * 搜索分类
 */
export type SearchCategory = 'paper' | 'patent' | 'general' | 'professional' | 'social' | 'developer' | 'wiki' | 'video'

/** Web-derived categories that use /api/v1/search/web endpoint */
export const WEB_CATEGORIES: ReadonlySet<SearchCategory> = new Set([
  'general', 'professional', 'social', 'developer', 'wiki', 'video',
])

/** All search categories in display order */
export const ALL_CATEGORIES: readonly SearchCategory[] = [
  'paper', 'patent', 'general', 'professional', 'social', 'developer', 'wiki', 'video',
]

/* ===== Skin System Types ===== */

/**
 * 皮肤配色方案定义
 * 每个方案对应一套配色（如深蓝、浅紫等）
 */
export interface SchemeDefinition {
  id: string
  labelKey: string
  dotColor: string
}

/**
 * 皮肤元数据和配置
 * 定义皮肤的标识、支持的方案、默认主题
 */
export interface SkinConfig {
  id: string
  labelKey: string
  descriptionKey: string
  defaultScheme: string
  defaultMode: Theme
  schemes: SchemeDefinition[]
}

/**
 * 皮肤运行时状态
 * 跟踪当前的主题和配色方案选择
 */
export interface SkinState {
  mode: Theme
  scheme: string
  toggleMode: () => void
  setScheme: (s: string) => void
  loadSkin: () => void
}

/**
 * 皮肤模块接口
 * 一个皮肤的完整导出：UI 组件、路由、配置、初始化函数
 */
export interface SkinModule {
  AppShell: React.ComponentType
  LoginPage: React.ComponentType
  skinRoutes: React.ReactNode
  skinConfig: SkinConfig
  ErrorBoundary: React.ComponentType<{ children: React.ReactNode }>
  ToastContainer: React.ComponentType
  Spinner: React.ComponentType<{ size?: 'sm' | 'md' | 'lg' }>
  bootstrap: () => void
}
