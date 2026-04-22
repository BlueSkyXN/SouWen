/**
 * 文件用途：数据规范化单元测试，验证各类搜索结果转换为统一格式
 *
 * 测试套件清单：
 *
 *     describe('normalizePaper')
 *         - 测试论文数据规范化
 *
 *         it('extracts author names from Author objects')
 *             - 验证：Author 对象数组转换为名字字符串数组
 *
 *         it('handles string authors gracefully')
 *             - 验证：支持字符串数组格式（向后兼容）
 *
 *         it('handles missing/null fields')
 *             - 验证：缺失字段设为空字符串或 null（年份、引用数）
 *
 *         it('prefers source_url over open_access_url')
 *             - 验证：URL 优先顺序正确
 *
 *         it('falls back to open_access_url')
 *             - 验证：source_url 空时回退
 *
 *     describe('normalizePatent')
 *         - 测试专利数据规范化
 *
 *         it('extracts fields from backend shape')
 *             - 验证：Applicant 对象数组转为逗号分隔字符串
 *
 *         it('handles empty applicants')
 *             - 验证：无申请人时返回空字符串
 *
 *         it('handles missing fields')
 *             - 验证：缺失字段设为默认值
 *
 *     describe('normalizeWeb')
 *         - 测试网页结果规范化
 *
 *         it('maps engine to source')
 *             - 验证：engine 字段映射到 source
 *
 *         it('handles missing engine')
 *             - 验证：缺失时设为空字符串
 *
 *     describe('normalizeDoctor')
 *         - 测试诊断数据源规范化
 *
 *         it('marks reachable when status is ok')
 *             - 验证：status='ok' 时 reachable=true，error=null
 *
 *         it('marks unreachable with error message')
 *             - 验证：status='error' 时 reachable=false，error 保留消息
 *
 *     describe('integrationTypeLabel')
 *         - 测试集成类型转中文标签
 *
 *         it('returns Chinese labels for integration types')
 *             - 验证：open_api→公开接口, scraper→爬虫抓取, official_api→授权接口, self_hosted→自托管
 *
 *     describe('typeLabel')
 *         - 测试类型转中文标签
 *
 *         it('returns Chinese labels for known types')
 *             - 验证：paper→论文, patent→专利, web→网页
 *
 *         it('returns raw value for unknown types')
 *             - 验证：未知类型直接返回原值
 */

import { describe, it, expect } from 'vitest'
import { normalizePaper, normalizePatent, normalizeWeb, normalizeDoctor, integrationTypeLabel, typeLabel } from '../lib/normalize'
import type { PaperResult, PatentResult, WebResult, DoctorSource } from '../types'

/**
 * 创建测试论文数据
 */
function makePaper(overrides: Partial<PaperResult> = {}): PaperResult {
  return {
    source: '', title: '', authors: [], source_url: '',
    ipc_codes: [], cpc_codes: [], applicants: [], inventors: [],
    patent_id: '', url: '', snippet: '', engine: '',
    ...overrides,
  } as PaperResult
}

/**
 * 创建测试专利数据
 */
function makePatent(overrides: Partial<PatentResult> = {}): PatentResult {
  return {
    source: '', title: '', patent_id: '', applicants: [],
    inventors: [], ipc_codes: [], cpc_codes: [], source_url: '',
    ...overrides,
  } as PatentResult
}

/**
 * 创建测试网页数据
 */
function makeWeb(overrides: Partial<WebResult> = {}): WebResult {
  return {
    source: '', title: '', url: '', snippet: '', engine: '',
    ...overrides,
  } as WebResult
}

/**
 * 创建测试诊断数据源
 */
function makeDoctor(overrides: Partial<DoctorSource> = {}): DoctorSource {
  return {
    name: '', category: 'paper', status: 'ok', integration_type: 'open_api',
    required_key: null, key_requirement: 'none', message: '', enabled: true,
    ...overrides,
  }
}

describe('normalizePaper', () => {
  /**
   * 测试：提取 Author 对象的名字
   */
  it('extracts author names from Author objects', () => {
    const result = normalizePaper(makePaper({
      title: 'Test Paper',
      authors: [{ name: 'Alice', affiliation: 'MIT' }, { name: 'Bob' }],
      year: 2024,
      doi: '10.1234/test',
      abstract: 'An abstract',
      source: 'openalex',
      source_url: 'https://example.com',
    }))
    expect(result.authors).toEqual(['Alice', 'Bob'])
    expect(result.year).toBe(2024)
    expect(result.url).toBe('https://example.com')
  })

  /**
   * 测试：处理字符串作者格式（向后兼容）
   */
  it('handles string authors gracefully', () => {
    const result = normalizePaper(makePaper({
      title: 'Old Format',
      authors: ['Alice', 'Bob'] as unknown as PaperResult['authors'],
      year: 2020,
    }))
    expect(result.authors).toEqual(['Alice', 'Bob'])
  })

  /**
   * 测试：处理缺失/null 字段
   */
  it('handles missing/null fields', () => {
    const result = normalizePaper(makePaper())
    expect(result.title).toBe('')
    expect(result.authors).toEqual([])
    expect(result.year).toBeNull()
    expect(result.doi).toBe('')
    expect(result.url).toBe('')
    expect(result.source).toBe('')
    expect(result.citationCount).toBeNull()
    expect(result.pdfUrl).toBe('')
  })

  /**
   * 测试：优先使用 source_url
   */
  it('prefers source_url over open_access_url', () => {
    const result = normalizePaper(makePaper({
      source_url: 'https://primary.com',
      open_access_url: 'https://fallback.com',
    }))
    expect(result.url).toBe('https://primary.com')
  })

  /**
   * 测试：回退到 open_access_url
   */
  it('falls back to open_access_url', () => {
    const result = normalizePaper(makePaper({
      source_url: '',
      open_access_url: 'https://fallback.com',
    }))
    expect(result.url).toBe('https://fallback.com')
  })
})

describe('normalizePatent', () => {
  /**
   * 测试：从后端格式提取字段
   */
  it('extracts fields from backend shape', () => {
    const result = normalizePatent(makePatent({
      title: 'My Patent',
      patent_id: 'US12345',
      applicants: [{ name: 'CorpA' }, { name: 'CorpB' }],
      inventors: ['Inv1', 'Inv2'],
      abstract: 'Patent abstract',
      source_url: 'https://pat.example.com',
      source: 'patentsview',
      publication_date: '2024-01-15',
    }))
    expect(result.patentNumber).toBe('US12345')
    expect(result.applicant).toBe('CorpA, CorpB')
    expect(result.inventors).toEqual(['Inv1', 'Inv2'])
    expect(result.url).toBe('https://pat.example.com')
    expect(result.publicationDate).toBe('2024-01-15')
  })

  /**
   * 测试：处理空申请人列表
   */
  it('handles empty applicants', () => {
    const result = normalizePatent(makePatent({ applicants: [] }))
    expect(result.applicant).toBe('')
  })

  /**
   * 测试：处理缺失字段
   */
  it('handles missing fields', () => {
    const result = normalizePatent(makePatent())
    expect(result.title).toBe('')
    expect(result.patentNumber).toBe('')
    expect(result.applicant).toBe('')
    expect(result.inventors).toEqual([])
    expect(result.url).toBe('')
  })
})

describe('normalizeWeb', () => {
  /**
   * 测试：engine 映射到 source
   */
  it('maps engine to source', () => {
    const result = normalizeWeb(makeWeb({
      title: 'Web Page',
      url: 'https://example.com',
      snippet: 'A snippet',
      engine: 'duckduckgo',
    }))
    expect(result.source).toBe('duckduckgo')
    expect(result.snippet).toBe('A snippet')
  })

  /**
   * 测试：处理缺失的 engine
   */
  it('handles missing engine', () => {
    const result = normalizeWeb(makeWeb({ title: 'X', url: 'u', snippet: 's', engine: '' }))
    expect(result.source).toBe('')
  })
})

describe('normalizeDoctor', () => {
  /**
   * 测试：status=ok 标记为可达
   */
  it('marks reachable when status is ok', () => {
    const result = normalizeDoctor(makeDoctor({
      name: 'openalex', category: 'paper', status: 'ok', integration_type: 'open_api',
    }))
    expect(result.reachable).toBe(true)
    expect(result.error).toBeNull()
  })

  /**
   * 测试：status=error 标记为不可达并保留错误消息
   */
  it('marks unreachable with error message', () => {
    const result = normalizeDoctor(makeDoctor({
      name: 'core', category: 'paper', status: 'error', integration_type: 'official_api',
      required_key: 'CORE_API_KEY', key_requirement: 'required', message: 'missing key',
    }))
    expect(result.reachable).toBe(false)
    expect(result.error).toBe('missing key')
  })
})

describe('integrationTypeLabel', () => {
  /**
   * 测试：集成类型转中文标签
   */
  it('returns Chinese labels for integration types', () => {
    expect(integrationTypeLabel('open_api')).toBe('公开接口')
    expect(integrationTypeLabel('scraper')).toBe('爬虫抓取')
    expect(integrationTypeLabel('official_api')).toBe('授权接口')
    expect(integrationTypeLabel('self_hosted')).toBe('自托管')
    expect(integrationTypeLabel('unknown')).toBe('unknown')
  })
})

describe('typeLabel', () => {
  /**
   * 测试：已知类型返回中文标签
   */
  it('returns Chinese labels for known types', () => {
    expect(typeLabel('paper')).toBe('论文')
    expect(typeLabel('patent')).toBe('专利')
    expect(typeLabel('general')).toBe('通用')
    expect(typeLabel('video')).toBe('视频')
  })

  /**
   * 测试：未知类型返回原值
   */
  it('returns raw value for unknown types', () => {
    expect(typeLabel('other')).toBe('other')
  })
})
