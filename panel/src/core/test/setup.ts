/**
 * 文件用途：测试环境初始化，配置 Vitest + React Testing Library 的全局 setup
 *
 * 初始化内容：
 *     - 导入 @testing-library/jest-dom/vitest，为 expect() 添加 DOM 匹配器
 *       （如 toBeInTheDocument()、toHaveClass() 等）
 */

import '@testing-library/jest-dom/vitest'
