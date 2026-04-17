/**
 * 文件用途：iOS 皮肤的路由配置，定义该皮肤的所有页面路由
 */

import { Route } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { SearchPage } from './pages/SearchPage'
import { SourcesPage } from './pages/SourcesPage'
import { NetworkPage } from './pages/NetworkPage'
import { ConfigPage } from './pages/ConfigPage'

export const skinRoutes = (
  <>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/search" element={<SearchPage />} />
    <Route path="/sources" element={<SourcesPage />} />
    <Route path="/network" element={<NetworkPage />} />
    <Route path="/config" element={<ConfigPage />} />
  </>
)
