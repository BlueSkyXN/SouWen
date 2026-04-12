import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { HTMLAttributes } from 'react'
import { SearchPage } from '../pages/SearchPage'
import { api } from '../services/api'
import { useNotificationStore } from '../stores/notificationStore'
import type { SearchResponse } from '../types'

vi.mock('../services/api', () => ({
  api: {
    getSources: vi.fn(),
    searchPaper: vi.fn(),
    searchPatent: vi.fn(),
    searchWeb: vi.fn(),
  },
}))

vi.mock('react-i18next', () => ({
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
        case 'search.failed':
          return `搜索失败: ${String(options?.message ?? '')}`
        case 'search.errorStateTitle':
          return '搜索失败'
        case 'search.resultCount':
          return `共 ${String(options?.count ?? 0)} 条结果`
        case 'search.success':
          return `搜索完成，共 ${String(options?.count ?? 0)} 条结果`
        default:
          return key
      }
    },
  }),
}))

vi.mock('framer-motion', () => ({
  m: {
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  },
}))

vi.mock('../components/common/Skeleton', () => ({
  ResultsSkeleton: () => <div>loading</div>,
}))

vi.mock('../components/common/MultiSelect', () => ({
  MultiSelect: ({ placeholder }: { placeholder: string }) => <div>{placeholder}</div>,
}))

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

  it('ignores stale results from an older superseded search', async () => {
    const first = deferred<SearchResponse>()
    const second = deferred<SearchResponse>()
    mockedApi.searchPaper
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    render(<SearchPage />)
    const user = userEvent.setup()
    const input = screen.getByRole('textbox')

    await user.type(input, 'first query')
    await user.click(screen.getByRole('button', { name: '搜索' }))
    expect(screen.getByText('loading')).toBeInTheDocument()

    await user.clear(input)
    await user.type(input, 'second query')
    await user.click(screen.getByRole('button', { name: '搜索中...' }))

    second.resolve(createPaperResponse('second query', 'Second result'))
    expect(await screen.findByText('Second result')).toBeInTheDocument()

    first.resolve(createPaperResponse('first query', 'First result'))
    await waitFor(() => {
      expect(screen.queryByText('First result')).not.toBeInTheDocument()
    })
  })
})
