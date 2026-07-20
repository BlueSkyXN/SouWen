/**
 * 搜索结果导出工具
 *
 * 提供 CSV、XLS 和 Markdown 格式导出，无需外部依赖。
 * XLS 使用 HTML 表格格式，所有主流电子表格软件均可打开。
 * Markdown 兼容 Obsidian / Logseq 的普通 Markdown、frontmatter 和属性语法。
 */

import type { NormalizedPaper, NormalizedPatent, NormalizedWeb } from './normalize'
import type { SearchMediaItem } from './searchMedia'

/** 导出列定义 */
interface Column<T> {
  header: string
  accessor: (item: T) => string
}

const PAPER_COLUMNS: Column<NormalizedPaper>[] = [
  { header: '标题', accessor: (p) => p.title },
  { header: '作者', accessor: (p) => p.authors.join('; ') },
  { header: '年份', accessor: (p) => p.year?.toString() ?? '' },
  { header: 'DOI', accessor: (p) => p.doi },
  { header: '引用数', accessor: (p) => p.citationCount?.toString() ?? '' },
  { header: '摘要', accessor: (p) => p.abstract },
  { header: '链接', accessor: (p) => p.url },
  { header: 'PDF', accessor: (p) => p.pdfUrl },
  { header: '来源', accessor: (p) => p.source },
]

const PATENT_COLUMNS: Column<NormalizedPatent>[] = [
  { header: '标题', accessor: (p) => p.title },
  { header: '专利号', accessor: (p) => p.patentNumber },
  { header: '申请人', accessor: (p) => p.applicant },
  { header: '发明人', accessor: (p) => p.inventors.join('; ') },
  { header: '公开日期', accessor: (p) => p.publicationDate },
  { header: '摘要', accessor: (p) => p.abstract },
  { header: '链接', accessor: (p) => p.url },
  { header: '来源', accessor: (p) => p.source },
]

const WEB_COLUMNS: Column<NormalizedWeb>[] = [
  { header: '标题', accessor: (w) => w.title },
  { header: '链接', accessor: (w) => w.url },
  { header: '摘要', accessor: (w) => w.snippet },
  { header: '来源', accessor: (w) => w.source },
]

const MEDIA_COLUMNS: Column<SearchMediaItem>[] = [
  { header: '类型', accessor: (m) => m.kind },
  { header: '标题', accessor: (m) => m.title },
  { header: '链接', accessor: (m) => m.url },
  { header: '缩略图', accessor: (m) => m.thumbnailUrl },
  { header: '来源', accessor: (m) => m.source },
  { header: '摘要', accessor: (m) => m.description },
  { header: '时长', accessor: (m) => m.duration },
  { header: '元数据', accessor: (m) => m.meta },
]

interface MarkdownField {
  label: string
  value: string
}

interface MarkdownEntry {
  title: string
  url?: string
  summary?: string
  fields: MarkdownField[]
  tag: string
}

/** CSV 转义：包含逗号、引号或换行的字段用双引号包裹 */
function csvEscape(value: string): string {
  if (/[,"\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function markdownEscape(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\[/g, '\\[')
    .replace(/\]/g, '\\]')
    .replace(/\*/g, '\\*')
    .replace(/_/g, '\\_')
    .replace(/`/g, '\\`')
    .replace(/#/g, '\\#')
}

function cleanMarkdownValue(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

function markdownLine(label: string, value: string): string | null {
  const clean = cleanMarkdownValue(value)
  if (!clean) return null
  return `- ${label}:: ${markdownEscape(clean)}`
}

function markdownLink(title: string, url?: string): string {
  const cleanTitle = cleanMarkdownValue(title) || 'Untitled'
  const escapedTitle = markdownEscape(cleanTitle)
  const cleanUrl = cleanMarkdownValue(url ?? '')
  return cleanUrl ? `[${escapedTitle}](${cleanUrl})` : escapedTitle
}

function toKnowledgeMarkdown(kind: string, entries: MarkdownEntry[]): string {
  const created = new Date().toISOString()
  const blocks = entries.map((entry, index) => {
    const lines = [
      `## ${index + 1}. ${markdownLink(entry.title, entry.url)}`,
      '',
      ...entry.fields
        .map((field) => markdownLine(field.label, field.value))
        .filter((line): line is string => line !== null),
    ]
    const summary = cleanMarkdownValue(entry.summary ?? '')
    if (summary) {
      lines.push('', markdownEscape(summary))
    }
    lines.push('', `#souwen/${entry.tag}`)
    return lines.join('\n')
  })

  return [
    '---',
    'source: SouWen',
    `kind: ${kind}`,
    `created: ${created}`,
    'format: obsidian-logseq',
    '---',
    '',
    `# SouWen ${kind} results`,
    '',
    ...blocks,
    '',
  ].join('\n')
}

function paperMarkdownEntries(items: NormalizedPaper[]): MarkdownEntry[] {
  return items.map((item) => ({
    title: item.title,
    url: item.url,
    summary: item.abstract,
    tag: 'paper',
    fields: [
      { label: 'source', value: item.source },
      { label: 'authors', value: item.authors.join('; ') },
      { label: 'year', value: item.year?.toString() ?? '' },
      { label: 'doi', value: item.doi },
      { label: 'citations', value: item.citationCount?.toString() ?? '' },
      { label: 'pdf', value: item.pdfUrl },
    ],
  }))
}

function patentMarkdownEntries(items: NormalizedPatent[]): MarkdownEntry[] {
  return items.map((item) => ({
    title: item.title,
    url: item.url,
    summary: item.abstract,
    tag: 'patent',
    fields: [
      { label: 'source', value: item.source },
      { label: 'patent', value: item.patentNumber },
      { label: 'applicant', value: item.applicant },
      { label: 'inventors', value: item.inventors.join('; ') },
      { label: 'publication', value: item.publicationDate },
    ],
  }))
}

function webMarkdownEntries(items: NormalizedWeb[]): MarkdownEntry[] {
  return items.map((item) => ({
    title: item.title,
    url: item.url,
    summary: item.snippet,
    tag: 'web',
    fields: [
      { label: 'source', value: item.source },
      { label: 'url', value: item.url },
    ],
  }))
}

function mediaMarkdownEntries(items: SearchMediaItem[]): MarkdownEntry[] {
  return items.map((item) => ({
    title: item.title,
    url: item.url,
    summary: item.description,
    tag: item.kind,
    fields: [
      { label: 'type', value: item.kind },
      { label: 'source', value: item.source },
      { label: 'thumbnail', value: item.thumbnailUrl },
      { label: 'duration', value: item.duration },
      { label: 'meta', value: item.meta },
    ],
  }))
}

/** 生成 CSV 字符串 */
function toCSV<T>(items: T[], columns: Column<T>[]): string {
  const header = columns.map((c) => csvEscape(c.header)).join(',')
  const rows = items.map((item) =>
    columns.map((c) => csvEscape(c.accessor(item))).join(','),
  )
  return [header, ...rows].join('\r\n')
}

/** 生成 XLS HTML 表格 */
function toXLSHtml<T>(items: T[], columns: Column<T>[]): string {
  const escapeHtml = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  const headerRow = columns.map((c) => `<th>${escapeHtml(c.header)}</th>`).join('')
  const dataRows = items
    .map(
      (item) =>
        '<tr>' +
        columns.map((c) => `<td>${escapeHtml(c.accessor(item))}</td>`).join('') +
        '</tr>',
    )
    .join('\n')

  return `<?xml version="1.0" encoding="UTF-8"?>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:x="urn:schemas-microsoft-com:office:excel"
      xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="UTF-8"/></head>
<body><table border="1">
<thead><tr>${headerRow}</tr></thead>
<tbody>${dataRows}</tbody>
</table></body></html>`
}

/** 触发浏览器文件下载 */
function downloadBlob(content: string, filename: string, mimeType: string) {
  const BOM = '\uFEFF'
  const blob = new Blob([BOM + content], { type: `${mimeType};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 获取当前时间戳字符串 (yyyyMMdd_HHmmss) */
function timestamp(): string {
  const now = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
}

// ─── Public API ───

export type ExportFormat = 'csv' | 'xls' | 'markdown'

export function exportPapers(items: NormalizedPaper[], format: ExportFormat = 'csv') {
  const ts = timestamp()
  if (format === 'csv') {
    downloadBlob(toCSV(items, PAPER_COLUMNS), `souwen_papers_${ts}.csv`, 'text/csv')
  } else if (format === 'xls') {
    downloadBlob(toXLSHtml(items, PAPER_COLUMNS), `souwen_papers_${ts}.xls`, 'application/vnd.ms-excel')
  } else {
    downloadBlob(toKnowledgeMarkdown('paper', paperMarkdownEntries(items)), `souwen_papers_${ts}.md`, 'text/markdown')
  }
}

export function exportPatents(items: NormalizedPatent[], format: ExportFormat = 'csv') {
  const ts = timestamp()
  if (format === 'csv') {
    downloadBlob(toCSV(items, PATENT_COLUMNS), `souwen_patents_${ts}.csv`, 'text/csv')
  } else if (format === 'xls') {
    downloadBlob(toXLSHtml(items, PATENT_COLUMNS), `souwen_patents_${ts}.xls`, 'application/vnd.ms-excel')
  } else {
    downloadBlob(toKnowledgeMarkdown('patent', patentMarkdownEntries(items)), `souwen_patents_${ts}.md`, 'text/markdown')
  }
}

export function exportWebResults(items: NormalizedWeb[], format: ExportFormat = 'csv') {
  const ts = timestamp()
  if (format === 'csv') {
    downloadBlob(toCSV(items, WEB_COLUMNS), `souwen_web_${ts}.csv`, 'text/csv')
  } else if (format === 'xls') {
    downloadBlob(toXLSHtml(items, WEB_COLUMNS), `souwen_web_${ts}.xls`, 'application/vnd.ms-excel')
  } else {
    downloadBlob(toKnowledgeMarkdown('web', webMarkdownEntries(items)), `souwen_web_${ts}.md`, 'text/markdown')
  }
}

export function exportMediaResults(items: SearchMediaItem[], format: ExportFormat = 'csv') {
  const ts = timestamp()
  if (format === 'csv') {
    downloadBlob(toCSV(items, MEDIA_COLUMNS), `souwen_media_${ts}.csv`, 'text/csv')
  } else if (format === 'xls') {
    downloadBlob(toXLSHtml(items, MEDIA_COLUMNS), `souwen_media_${ts}.xls`, 'application/vnd.ms-excel')
  } else {
    downloadBlob(toKnowledgeMarkdown('media', mediaMarkdownEntries(items)), `souwen_media_${ts}.md`, 'text/markdown')
  }
}
