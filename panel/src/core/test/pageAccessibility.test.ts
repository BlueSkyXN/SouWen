/**
 * 文件用途：跨 skin 页面可访问性静态回归测试。
 */

import { describe, expect, it } from 'vitest'

const SKINS = ['apple', 'carbon', 'ios', 'souwen-google', 'souwen-nebula'] as const
const CRITICAL_PAGES = ['LoginPage', 'SearchPage', 'VideoPage'] as const

const PAGE_SOURCES = import.meta.glob('../../skins/*/pages/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const NATIVE_CLICKABLE_TAGS = new Set([
  'a',
  'button',
  'input',
  'select',
  'textarea',
  'summary',
  'option',
])

interface ControlBlock {
  tag: string
  start: number
  block: string
}

function sourcePath(skin: typeof SKINS[number], page: typeof CRITICAL_PAGES[number]): string {
  return `../../skins/${skin}/pages/${page}.tsx`
}

function pageEntries(page: string): Array<[string, string]> {
  return Object.entries(PAGE_SOURCES).filter(([file]) => file.endsWith(`/pages/${page}.tsx`))
}

function findSelfClosingEnd(source: string, start: number): number {
  const selfClose = source.indexOf('/>', start)
  if (selfClose < 0) {
    const tagClose = source.indexOf('>', start)
    return tagClose < 0 ? source.length : tagClose + 1
  }
  return selfClose + 2
}

function formControlBlocks(source: string): ControlBlock[] {
  const controls: ControlBlock[] = []
  const pattern = /<(input|select|textarea|Input)\b/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source))) {
    const tag = match[1]
    const start = match.index
    let end = findSelfClosingEnd(source, start)

    if (tag === 'select' || tag === 'textarea') {
      const closingTag = `</${tag}>`
      const close = source.indexOf(closingTag, start)
      if (close >= 0) end = close + closingTag.length
    }

    controls.push({ tag, start, block: source.slice(start, end) })
  }

  return controls
}

function escapedRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function literalId(block: string): string | null {
  return block.match(/\bid=(["'])([^"']+)\1/)?.[2] ?? null
}

function bracedAttribute(block: string, attr: string): string | null {
  const marker = `${attr}={`
  const attrStart = block.indexOf(marker)
  if (attrStart < 0) return null

  let depth = 1
  const valueStart = attrStart + marker.length
  for (let i = valueStart; i < block.length; i += 1) {
    if (block[i] === '{') depth += 1
    if (block[i] === '}') depth -= 1
    if (depth === 0) return block.slice(valueStart, i)
  }
  return null
}

function hasLabelFor(source: string, id: string): boolean {
  return new RegExp(`<label\\b[\\s\\S]*?htmlFor=(["'])${escapedRegExp(id)}\\1`).test(source)
}

function hasLabelForExpression(source: string, expression: string): boolean {
  return source.includes(`htmlFor={${expression}}`)
}

function isWrappedByLabel(source: string, start: number): boolean {
  const before = source.slice(0, start)
  const labelStart = before.lastIndexOf('<label')
  if (labelStart < 0) return false

  const labelEnd = before.lastIndexOf('</label>')
  return labelEnd < labelStart && source.indexOf('</label>', start) >= 0
}

function translationCall(key: string): string[] {
  const translationFunction = 't'
  return [`${translationFunction}('${key}')`, `${translationFunction}("${key}")`]
}

function blockUsesTranslation(block: string, attr: string, key: string): boolean {
  return translationCall(key).some((call) => block.includes(`${attr}={${call}}`))
}

function controlHasAccessibleName(control: ControlBlock, source: string): boolean {
  const { tag, block, start } = control
  if (block.includes('type="hidden"') || block.includes("type='hidden'")) return true
  if (block.includes('aria-label=') || block.includes('aria-labelledby=')) return true
  if (tag === 'Input' && block.includes('label=')) return true

  const literal = literalId(block)
  if (literal && hasLabelFor(source, literal)) return true

  const expression = bracedAttribute(block, 'id')
  if (expression && hasLabelForExpression(source, expression)) return true

  return isWrappedByLabel(source, start)
}

function blockHasAccessibleName(block: string, source: string, key: string): boolean {
  if (blockUsesTranslation(block, 'aria-label', key)) return true
  if (block.includes('aria-labelledby=')) return true

  const id = literalId(block)
  return !!id && hasLabelFor(source, id)
}

function unlabeledPlaceholderInputs(file: string, source: string, key: string): string[] {
  return formControlBlocks(source)
    .filter((control) => control.tag === 'input')
    .filter((control) => blockUsesTranslation(control.block, 'placeholder', key))
    .filter((control) => !blockHasAccessibleName(control.block, source, key))
    .map((control) => `${file}:${lineNumber(source, control.start)} ${key}`)
}

function lineNumber(source: string, index: number): number {
  return source.slice(0, index).split('\n').length
}

function tablistBlocks(source: string): ControlBlock[] {
  const blocks: ControlBlock[] = []
  const pattern = /<([A-Za-z][A-Za-z0-9.]*)\b[^>]*role=(["'])tablist\2/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source))) {
    const start = match.index
    const tag = match[1]
    const tagClose = source.indexOf('>', start)
    const end = tagClose < 0 ? source.length : tagClose + 1
    blocks.push({ tag, start, block: source.slice(start, end) })
  }

  return blocks
}

function tablistHasAccessibleName(block: string): boolean {
  return block.includes('aria-label=') || block.includes('aria-labelledby=')
}

function scriptedLinkBlocks(source: string): ControlBlock[] {
  const blocks: ControlBlock[] = []
  const pattern = /<([A-Za-z][A-Za-z0-9.]*)\b[^>]*role=(["'])link\2/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source))) {
    const start = match.index
    const tag = match[1]
    const tagClose = source.indexOf('>', start)
    const end = tagClose < 0 ? source.length : tagClose + 1
    blocks.push({ tag, start, block: source.slice(start, end) })
  }

  return blocks
}

function nonNativeClickHandlerBlocks(source: string): ControlBlock[] {
  const blocks: ControlBlock[] = []
  const pattern = /<([A-Za-z][A-Za-z0-9.]*)\b(?=[^>]*\bonClick=)[^>]*>/g
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source))) {
    const tag = match[1]
    if (tag[0] === tag[0].toUpperCase() || NATIVE_CLICKABLE_TAGS.has(tag)) continue
    if (match[0].includes('styles.modalOverlay') || match[0].includes('styles.modalCard')) continue

    const start = match.index
    blocks.push({ tag, start, block: match[0] })
  }

  return blocks
}

describe('page accessibility source conventions', () => {
  it('loads every skin page covered by the accessibility checks', () => {
    const missing = SKINS.flatMap((skin) => (
      CRITICAL_PAGES.map((page) => sourcePath(skin, page)).filter((file) => !(file in PAGE_SOURCES))
    ))

    expect(missing).toEqual([])
  })

  it('keeps login inputs connected to stable labels', () => {
    const missing = pageEntries('LoginPage').flatMap(([file, source]) => (
      [
        ['login-server-url', 'server URL'],
        ['login-password', 'password'],
      ].flatMap(([id, field]) => (
        literalId(formControlBlocks(source).find((control) => control.block.includes(`id="${id}"`))?.block ?? '') === id
          && hasLabelFor(source, id)
          ? []
          : [`${file}: ${field}`]
      ))
    ))

    expect(missing).toEqual([])
  })

  it('gives placeholder-only search and video text inputs an accessible name', () => {
    const missing = [
      ...pageEntries('SearchPage').flatMap(([file, source]) => (
        unlabeledPlaceholderInputs(file, source, 'search.placeholder')
      )),
      ...pageEntries('VideoPage').flatMap(([file, source]) => (
        [
          ...unlabeledPlaceholderInputs(file, source, 'video.searchPlaceholder'),
          ...unlabeledPlaceholderInputs(file, source, 'video.bilibiliPlaceholder'),
        ]
      )),
    ].sort()

    expect(missing).toEqual([])
  })

  it('gives every native form control and shared Input component an accessible name', () => {
    const missing = Object.entries(PAGE_SOURCES).flatMap(([file, source]) => (
      formControlBlocks(source)
        .filter((control) => !controlHasAccessibleName(control, source))
        .map((control) => `${file}:${lineNumber(source, control.start)} <${control.tag}>`)
    )).sort()

    expect(missing).toEqual([])
  })

  it('gives tablists an accessible name', () => {
    const missing = Object.entries(PAGE_SOURCES).flatMap(([file, source]) => (
      tablistBlocks(source)
        .filter((control) => !tablistHasAccessibleName(control.block))
        .map((control) => `${file}:${lineNumber(source, control.start)} <${control.tag}>`)
    )).sort()

    expect(missing).toEqual([])
  })

  it('uses native anchors instead of scripted role=link elements', () => {
    const scripted = Object.entries(PAGE_SOURCES).flatMap(([file, source]) => (
      scriptedLinkBlocks(source)
        .map((control) => `${file}:${lineNumber(source, control.start)} <${control.tag}>`)
    )).sort()

    expect(scripted).toEqual([])
  })

  it('uses native controls for page click targets', () => {
    const scripted = Object.entries(PAGE_SOURCES).flatMap(([file, source]) => (
      nonNativeClickHandlerBlocks(source)
        .map((control) => `${file}:${lineNumber(source, control.start)} <${control.tag}>`)
    )).sort()

    expect(scripted).toEqual([])
  })
})
