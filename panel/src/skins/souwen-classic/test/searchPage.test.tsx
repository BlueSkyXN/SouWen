/**
 * 搜索页面单元测试
 *
 * 文件用途：测试 SearchPage 组件的核心交互和状态管理逻辑
 * 
 * 测试覆盖场景：
 *   1. 搜索失败时显示内联错误状态
 *   2. 多个搜索请求时，只显示最新请求的结果（忽略过期结果）
 *
 * 关键 Mock：
 *   - api.searchPaper/searchPatent/searchWeb - 搜索 API 方法
 *   - react-i18next - 国际化（返回中文标签）
 *   - framer-motion - 动画库（替换为无动画 div）
 *   - 共享组件 - Skeleton、MultiSelect、SegmentedControl 等（模拟实现）
 *
 * 辅助工具：
 *   - createPaperResponse() - 构造搜索响应对象
 *   - deferred<T>() - 创建 Promise 以便控制resolve/reject 时机，用于测试竞态条件
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { SearchPage } from '../pages/SearchPage'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import type { SearchResponse } from '@core/types'

// Mock API 模块
vi.mock('@core/services/api', () => ({
  api: {
    getSources: vi.fn(),
    searchPaper: vi.fn(),
    searchPatent: vi.fn(),
    searchWeb: vi.fn(),
  },
}))

// Mock 国际化库 - 返回对应中文标签
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      switch (key) {
        case 'search.papers':
          return '论文'
        case 'search.patents':
          return '专利'
        case 'search.web':
          return '网页'
        case 'search.placeholder':
          return '输入搜索关键词...'
        case 'search.button':
          return '搜索'
        case 'search.searching':
          return '搜索中...'
        case 'search.items':
          return `${String(options?.count ?? 0)} 条`
        case 'search.sources':
          return '数据源'
        case 'search.engines':
          return '搜索引擎'
        case 'search.startSearch':
          return '输入关键词开始搜索'
        case 'search.enterKeyword':
          return '探索学术知识'
        case 'search.startSearchDesc':
          return '选择数据源，输入关键词，探索学术世界'
        case 'search.failed':
          return `搜索失败: ${String(options?.message ?? '')}`
        case 'search.errorStateTitle':
          return '搜索失败'
        case 'search.resultCount':
          return `共 ${String(options?.count ?? 0)} 条结果`
        case 'search.success':
          return `搜索完成，共 ${String(options?.count ?? 0)} 条结果`
        case 'search.searchScope':
          return '搜索范围'
        case 'search.searchingHint':
          return '正在搜索...'
        case 'search.retrySearch':
          return '重试搜索'
        case 'search.source_openalex':
          return '开放学术图谱'
        case 'search.source_arxiv':
          return '预印本'
        case 'search.source_google_patents':
          return '实验性爬虫'
        case 'search.source_duckduckgo':
          return '爬虫'
        case 'search.source_bing':
          return '爬虫'
        default:
          return key
      }
    },
  }),
}))

// Mock 动画库 - 用普通 div 替换动画组件
vi.mock('framer-motion', () => ({
  m: {
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
    form: ({ children, ...props }: HTMLAttributes<HTMLFormElement>) => <form {...props}>{children}</form>,
    article: ({ children, ...props }: HTMLAttributes<HTMLElement>) => <article {...props}>{children}</article>,
  },
}))

// Mock 骨架屏组件
vi.mock('../components/common/Skeleton', () => ({
  ResultsSkeleton: () => <div>loading</div>,
}))

// Mock 多选组件
vi.mock('../components/common/MultiSelect', () => ({
  MultiSelect: ({ placeholder }: { placeholder: string }) => <div>{placeholder}</div>,
}))

// Mock 分段控制组件
vi.mock('../components/common/SegmentedControl', () => ({
  SegmentedControl: ({ options, value, onChange }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void }) => (
    <div role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  ),
}))

// Mock 徽章组件
vi.mock('../components/common/Badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

// Mock 空状态组件
vi.mock('../components/common/EmptyState', () => ({
  EmptyState: ({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) => (
    <div>
      <span>{title}</span>
      {description && <span>{description}</span>}
      {action}
    </div>
  ),
}))

/**
 * 构造搜索响应对象
 * @param query - 搜索查询词
 * @param title - 结果标题
 * @returns SearchResponse 对象
 */
function createPaperResponse(query: string, title: string): SearchResponse {
  return {
    query,
    sources: ['openalex'],
    total: 1,
    results: [
      {
        query,
        source: 'openalex',
        total_results: 1,
        results: [
          {
            source: 'openalex',
            title,
            authors: [],
            source_url: `https://example.com/${encodeURIComponent(title)}`,
          },
        ],
      },
    ],
  }
}

/**
 * 创建可控延迟 Promise
 * @returns { promise, resolve, reject } - 返回 Promise 及其控制方法
 * 
 * 用于测试竞态条件：先发起 A 请求，再发起 B 请求，
 * 然后先 resolve B 再 resolve A，验证组件只显示 B 的结果
 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('SearchPage', () => {
  const mockedApi = vi.mocked(api)

  beforeEach(() => {
    vi.clearAllMocks()
    useNotificationStore.setState({ toasts: [] })
    mockedApi.getSources.mockResolvedValue({ paper: [], patent: [], web: [] })
  })

  // 测试用例 1：搜索失败时显示内联错误状态
  it('shows an inline failure state when a search fails', async () => {
    mockedApi.searchPaper.mockRejectedValue(new Error('rate limited'))

    render(<SearchPage />)
    const user = userEvent.setup()

    await user.type(screen.getByRole('textbox'), 'quantum')
    await user.click(screen.getByRole('button', { name: '搜索' }))

    expect(await screen.findByText('搜索失败')).toBeInTheDocument()
    expect(screen.getByText('rate limited')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '搜索' })).toBeEnabled()
  })

  // 测试用例 2：多个请求时，忽略过期结果（保留最新结果）
  it('ignores stale results from an older superseded search', async () => {
    // 创建两个可控的 Promise：第一个搜索和第二个搜索
    const first = deferred<SearchResponse>()
    const second = deferred<SearchResponse>()
    mockedApi.searchPaper
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    render(<SearchPage />)
    const user = userEvent.setup()
    const input = screen.getByRole('textbox')

    // 第一次搜索
    await user.type(input, 'first query')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    expect(screen.getByText('loading')).toBeInTheDocument()

    // 第二次搜索（未等待第一个完成）
    await user.clear(input)
    await user.type(input, 'second query')
    await user.click(screen.getByRole('button', { name: '搜索' }))

    // 先 resolve 第二个搜索
    second.resolve(createPaperResponse('second query', 'Second result'))
    expect(await screen.findByText('Second result')).toBeInTheDocument()

    // 后 resolve 第一个搜索 - 应该被忽略
    first.resolve(createPaperResponse('first query', 'First result'))
    await waitFor(() => {
      expect(screen.queryByText('First result')).not.toBeInTheDocument()
    })
  })
})
