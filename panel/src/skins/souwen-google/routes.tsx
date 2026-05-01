/**
 * 路由定义文件 - skin 的页面路由表
 *
 * 文件用途：定义 souwen-google skin 的所有应用页面路由，包括控制板、搜索、抓取、资源、网络、配置
 *
 * 路由清单：
 *   / → DashboardPage - 应用首页/控制面板
 *   /search → SearchPage - 论文/专利/网页综合搜索
 *   /fetch → FetchPage - 网页内容抓取
 *   /sources → SourcesPage - 数据源管理和状态检测
 *   /network → NetworkPage - 网络设置和后端配置
 *   /config → ConfigPage - 应用配置查看和编辑
 *
 * 导出格式：JSX Fragment 包含 <Route> 元素，由父 Router 组件加载
 */

import { Route, Navigate } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { SearchPage } from './pages/SearchPage'
import { FetchPage } from './pages/FetchPage'
import { VideoPage } from './pages/VideoPage'
import { ToolsPage } from './pages/ToolsPage'
import { SourcesPage } from './pages/SourcesPage'
import { NetworkPage } from './pages/NetworkPage'
import { ConfigPage } from './pages/ConfigPage'
import { WarpPage } from './pages/WarpPage'
import { PluginsPage } from './pages/PluginsPage'

export const skinRoutes = (
  <>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/search" element={<Navigate to="/search/paper" replace />} />
    <Route path="/search/:domain" element={<SearchPage />} />
    <Route path="/fetch" element={<FetchPage />} />
    <Route path="/video" element={<VideoPage />} />
    <Route path="/tools" element={<ToolsPage />} />
    <Route path="/sources" element={<SourcesPage />} />
    <Route path="/network" element={<NetworkPage />} />
    <Route path="/warp" element={<WarpPage />} />
    <Route path="/config" element={<ConfigPage />} />
    <Route path="/plugins" element={<PluginsPage />} />
  </>
)
