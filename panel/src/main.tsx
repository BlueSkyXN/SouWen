/**
 * 文件用途：应用入口点，负责初始化皮肤系统、国际化、应用引导
 *
 * 函数/流程清单：
 *     Bootstrap 初始化序列
 *         - 从本地存储读取保存的皮肤 ID（默认使用系统默认皮肤）
 *         - 应用皮肤到 DOM 根元素的 data-skin 属性（在首次渲染前同步完成）
 *         - 纠正无效/过期的皮肤 ID 并持久化
 *         - 调用皮肤模块的 bootstrap() 方法加载样式与主题
 *         - 挂载 React 应用与错误边界
 *
 * 模块依赖：
 *     - react: React 库用于渲染应用
 *     - react-dom: React DOM 挂载 API
 *     - @core/i18n: 国际化初始化（i18next）
 *     - virtual:skin-loader: Vite 虚拟模块，加载皮肤 CSS 与注册可用皮肤
 *     - @core/skin-registry: 皮肤系统管理函数
 *
 * 关键逻辑：
 *     - 所有初始化在 React 首次渲染前同步完成，确保 data-skin 属性在 DOM 加载时就已设置
 *     - 这避免了皮肤闪烁（浏览器先显示默认样式再切换皮肤）
 *     - 无效皮肤 ID 会被自动纠正并保存，保证下次加载时的一致性
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@core/i18n'
import 'virtual:skin-loader'
import { getSkinOrDefault, getDefaultSkinId, setActiveSkinId } from '@core/skin-registry'
import App from './App'

// 同步引导 — 在首次渲染前应用皮肤属性
const savedSkinId = localStorage.getItem('souwen_skin') || getDefaultSkinId()
const activeSkin = getSkinOrDefault(savedSkinId)
setActiveSkinId(activeSkin.id)
document.documentElement.setAttribute('data-skin', activeSkin.id)

// 纠正无效/过期的皮肤 ID 并保存
if (savedSkinId !== activeSkin.id) {
  localStorage.setItem('souwen_skin', activeSkin.id)
}

// 从本地存储加载明暗模式/配色方案并同步应用到 DOM
activeSkin.skinModule.bootstrap()

const { ErrorBoundary } = activeSkin.skinModule

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
