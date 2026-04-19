/**
 * 文件用途：Apple 皮肤的路由配置，定义该皮肤的所有页面路由
 *
 * 路由清单：
 *   / - DashboardPage（首页/仪表板）
 *   /search - SearchPage（搜索页面）
 *   /fetch - FetchPage（网页抓取页面）
 *   /sources - SourcesPage（数据源管理页面）
 *   /network - NetworkPage（网络连接页面）
 *   /config - ConfigPage（应用配置页面）
 *
 * 模块依赖：
 *   - react-router-dom: Route 组件用于定义路由
 *   - 各 page 组件：每个页面组件
 */

import { Route } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { SearchPage } from './pages/SearchPage'
import { FetchPage } from './pages/FetchPage'
import { SourcesPage } from './pages/SourcesPage'
import { NetworkPage } from './pages/NetworkPage'
import { ConfigPage } from './pages/ConfigPage'

/**
 * Apple 皮肤的路由配置
 * 返回一个 React Router Route 片段，由主应用在初始化时嵌入到路由树中
 * 这种结构允许不同皮肤定义不同的页面组件，同时保持路径和功能的一致性
 */
export const skinRoutes = (
  <>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/search" element={<SearchPage />} />
    <Route path="/fetch" element={<FetchPage />} />
    <Route path="/sources" element={<SourcesPage />} />
    <Route path="/network" element={<NetworkPage />} />
    <Route path="/config" element={<ConfigPage />} />
  </>
)
