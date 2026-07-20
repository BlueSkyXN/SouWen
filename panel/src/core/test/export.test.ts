/**
 * 文件用途：搜索结果导出工具回归测试。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { exportMediaResults, exportPapers, exportWebResults } from '../lib/export'

describe('search result export helpers', () => {
  let capturedBlob: Blob | null = null
  let capturedDownload = ''

  afterEach(() => {
    vi.restoreAllMocks()
    capturedBlob = null
    capturedDownload = ''
  })

  function mockDownload() {
    if (!('createObjectURL' in URL)) {
      Object.defineProperty(URL, 'createObjectURL', {
        configurable: true,
        value: () => 'blob:souwen-media',
      })
    }
    if (!('revokeObjectURL' in URL)) {
      Object.defineProperty(URL, 'revokeObjectURL', {
        configurable: true,
        value: () => {},
      })
    }
    vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
      capturedBlob = blob as Blob
      return 'blob:souwen-media'
    })
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => {
      if (node instanceof HTMLAnchorElement) capturedDownload = node.download
      return node
    })
    vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node)
  }

  it('exports image and video fields instead of normal web columns', async () => {
    mockDownload()

    exportMediaResults([
      {
        kind: 'video',
        title: 'System demo',
        url: 'https://video.example/watch',
        thumbnailUrl: 'https://img.example/video.jpg',
        source: 'Demo Channel',
        description: 'Short demo',
        duration: '03:21',
        meta: '2026-06-28',
      },
    ])

    expect(capturedBlob).not.toBeNull()
    const text = await capturedBlob!.text()
    expect(text).toContain('类型,标题,链接,缩略图,来源,摘要,时长,元数据')
    expect(text).toContain('video,System demo,https://video.example/watch')
    expect(text).toContain('https://img.example/video.jpg')
    expect(text).toContain('03:21')
  })

  it('exports papers as Obsidian and Logseq friendly Markdown', async () => {
    mockDownload()

    exportPapers([
      {
        title: 'Graph Retrieval [RAG]',
        authors: ['Ada Lovelace', 'Grace Hopper'],
        year: 2026,
        doi: '10.1234/example',
        abstract: 'A compact retrieval note with #hash and inline `code`.',
        url: 'https://paper.example/rag',
        source: 'openalex',
        citationCount: 42,
        pdfUrl: 'https://paper.example/rag.pdf',
      },
    ], 'markdown')

    expect(capturedBlob).not.toBeNull()
    expect(capturedDownload).toMatch(/^souwen_papers_.*\.md$/)
    const text = await capturedBlob!.text()
    expect(text).toContain('format: obsidian-logseq')
    expect(text).toContain('# SouWen paper results')
    expect(text).toContain('## 1. [Graph Retrieval \\[RAG\\]](https://paper.example/rag)')
    expect(text).toContain('- authors:: Ada Lovelace; Grace Hopper')
    expect(text).toContain('- doi:: 10.1234/example')
    expect(text).toContain('- citations:: 42')
    expect(text).toContain('- pdf:: https://paper.example/rag.pdf')
    expect(text).toContain('A compact retrieval note with \\#hash and inline \\`code\\`.')
    expect(text).toContain('#souwen/paper')
  })

  it('exports web results as Markdown with source and url properties', async () => {
    mockDownload()

    exportWebResults([
      {
        title: 'SouWen docs',
        url: 'https://docs.example/souwen',
        snippet: 'Documentation result',
        source: 'duckduckgo',
      },
    ], 'markdown')

    expect(capturedBlob).not.toBeNull()
    expect(capturedDownload).toMatch(/^souwen_web_.*\.md$/)
    const text = await capturedBlob!.text()
    expect(text).toContain('# SouWen web results')
    expect(text).toContain('## 1. [SouWen docs](https://docs.example/souwen)')
    expect(text).toContain('- source:: duckduckgo')
    expect(text).toContain('- url:: https://docs.example/souwen')
    expect(text).toContain('Documentation result')
    expect(text).toContain('#souwen/web')
  })
})
