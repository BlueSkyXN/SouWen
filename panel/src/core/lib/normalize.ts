/**
 * 文件用途：数据规范化模块，统一来自多个后端源的搜索结果格式
 *
 * 接口/函数清单：
 *     NormalizedPaper（接口）
 *         - 功能：论文结果的统一内部格式
 *         - 关键字段：title 标题, authors[] 作者列表, year 年份, doi DOI 标识符,
 *                    abstract 摘要, url 链接, source 数据源, citationCount 引用数, pdfUrl PDF 链接
 *
 *     NormalizedPatent（接口）
 *         - 功能：专利结果的统一内部格式
 *         - 关键字段：title 名称, patentNumber 专利号, applicant 申请人, inventors[] 发明人,
 *                    abstract 摘要, url 链接, source 数据源, publicationDate 公开日期
 *
 *     NormalizedWeb（接口）
 *         - 功能：网页搜索结果的统一内部格式
 *         - 关键字段：title 页标题, url 链接, snippet 摘要文本, source 搜索引擎名
 *
 *     NormalizedSource（接口）
 *         - 功能：数据源可达性和配置状态
 *         - 关键字段：name 源名称, type 源类型（paper/patent/web）, integration_type 集成类型,
 *                    reachable 是否可用, error 错误消息
 *
 *     normalizePaper(raw: PaperResult) -> NormalizedPaper
 *         - 功能：转换后端论文数据为规范格式
 *         - 处理逻辑：
 *           - 作者列表支持对象数组（含 name、affiliation）和字符串数组两种格式
 *           - 年份、引用数等数值字段缺失时设为 null
 *           - URL 优先使用 source_url，回退到 open_access_url
 *
 *     normalizePatent(raw: PatentResult) -> NormalizedPatent
 *         - 功能：转换后端专利数据为规范格式
 *         - 处理逻辑：申请人列表转换为逗号分隔的单一字符串
 *
 *     normalizeWeb(raw: WebResult) -> NormalizedWeb
 *         - 功能：转换搜索引擎结果为规范格式
 *         - 处理逻辑：engine 字段映射到 source
 *
 *     normalizeDoctor(raw: DoctorSource) -> NormalizedSource
 *         - 功能：规范化诊断系统数据源信息
 *         - 处理逻辑：status='ok' 为可达，否则标记不可达并保留错误消息
 *
 *     integrationTypeLabel(integration_type: string) -> string
 *         - 功能：将集成类型标识符转换为显示标签
 *         - 输出：公开接口 / 爬虫抓取 / 授权接口 / 自托管 等格式
 *
 *     typeLabel(type: string) -> string
 *         - 功能：将源类型转换为用户可读的中文标签
 *         - 逻辑：paper → 论文, patent → 专利, web → 网页（调用 i18n）
 *
 * 模块依赖：
 *     - ../types: 后端数据结构定义
 *     - ../i18n: 国际化（标签翻译）
 */

import type { PaperResult, PatentResult, WebResult, DoctorSource, SourceCategory } from '../types'
import i18n from '../i18n'
import { isDoctorStatusAvailable } from './sourceStatus'

/**
 * 论文搜索结果规范格式
 * 所有论文源数据都转换为此统一格式，便于 UI 组件统一处理
 */
export interface NormalizedPaper {
  title: string
  authors: string[]
  year: number | null
  doi: string
  abstract: string
  url: string
  source: string
  citationCount: number | null
  pdfUrl: string
}

/**
 * 专利搜索结果规范格式
 */
export interface NormalizedPatent {
  title: string
  patentNumber: string
  applicant: string
  inventors: string[]
  abstract: string
  url: string
  source: string
  publicationDate: string
}

/**
 * 网页搜索结果规范格式
 */
export interface NormalizedWeb {
  title: string
  url: string
  snippet: string
  source: string
}

/**
 * 数据源状态和配置信息规范格式
 */
export interface NormalizedSource {
  name: string
  type: SourceCategory
  integration_type: string
  key_requirement: 'none' | 'optional' | 'required' | 'self_hosted'
  risk_level: 'low' | 'medium' | 'high'
  distribution: 'core' | 'extra' | 'plugin'
  stability: 'stable' | 'beta' | 'experimental' | 'deprecated'
  reachable: boolean
  error: string | null
}

/**
 * 规范化论文数据
 * 处理作者对象/字符串混合、URL 多源回退、数值字段的 null 处理
 */
export function normalizePaper(raw: PaperResult): NormalizedPaper {
  const authors = Array.isArray(raw.authors)
    ? raw.authors
        .map((a) => (typeof a === 'string' ? a : a?.name ?? ''))
        .filter(Boolean)
    : []
  return {
    title: raw.title?.trim() || '',
    authors,
    year: typeof raw.year === 'number' ? raw.year : null,
    doi: raw.doi?.trim() || '',
    abstract: raw.abstract?.trim() || '',
    url: raw.source_url?.trim() || raw.open_access_url?.trim() || '',
    source: typeof raw.source === 'string' ? raw.source : '',
    citationCount: typeof raw.citation_count === 'number' ? raw.citation_count : null,
    pdfUrl: raw.pdf_url?.trim() || '',
  }
}

/**
 * 规范化专利数据
 * 申请人列表合并为单一字符串（逗号分隔）
 */
export function normalizePatent(raw: PatentResult): NormalizedPatent {
  const applicant = Array.isArray(raw.applicants) && raw.applicants.length > 0
    ? raw.applicants.map((a) => (typeof a === 'string' ? a : a?.name ?? '')).filter(Boolean).join(', ')
    : ''
  return {
    title: raw.title?.trim() || '',
    patentNumber: raw.patent_id?.trim() || '',
    applicant,
    inventors: Array.isArray(raw.inventors) ? raw.inventors.filter(Boolean) : [],
    abstract: raw.abstract?.trim() || '',
    url: raw.source_url?.trim() || '',
    source: typeof raw.source === 'string' ? raw.source : '',
    publicationDate: raw.publication_date?.trim() || '',
  }
}

/**
 * 规范化网页搜索结果
 */
export function normalizeWeb(raw: WebResult): NormalizedWeb {
  return {
    title: raw.title?.trim() || '',
    url: raw.url?.trim() || '',
    snippet: raw.snippet?.trim() || '',
    source: raw.engine || '',
  }
}

/**
 * 规范化诊断系统数据源信息
 */
export function normalizeDoctor(raw: DoctorSource): NormalizedSource {
  const reachable = isDoctorStatusAvailable(raw.status)
  return {
    name: raw.name || '',
    type: raw.category || 'paper',
    integration_type: typeof raw.integration_type === 'string' ? raw.integration_type : 'open_api',
    key_requirement: raw.key_requirement || 'none',
    risk_level: raw.risk_level || 'low',
    distribution: raw.distribution || 'core',
    stability: raw.stability || 'stable',
    reachable,
    error: reachable ? null : raw.message || null,
  }
}

/**
 * 格式化集成类型为显示标签
 */
export function integrationTypeLabel(integration_type: string): string {
  switch (integration_type) {
    case 'open_api': return '公开接口'
    case 'scraper': return '爬虫抓取'
    case 'official_api': return '授权接口'
    case 'self_hosted': return '自托管'
    default: return integration_type
  }
}

/**
 * 将源类型转换为中文标签
 */
export function typeLabel(type: string): string {
  switch (type) {
    case 'paper': return i18n.t('common.paper')
    case 'patent': return i18n.t('common.patent')
    case 'web_general': return i18n.t('common.web_general')
    case 'web_professional': return i18n.t('common.web_professional')
    case 'social': return i18n.t('common.social')
    case 'office': return i18n.t('common.office')
    case 'developer': return i18n.t('common.developer')
    case 'knowledge': return i18n.t('common.knowledge')
    case 'cn_tech': return i18n.t('common.cn_tech')
    case 'video': return i18n.t('common.video')
    case 'archive': return i18n.t('common.archive')
    case 'fetch': return i18n.t('common.fetch')
    default: return type
  }
}
