/**
 * 文件用途：跨 skin layout 可访问性静态回归测试。
 */

import { describe, expect, it } from 'vitest'

const LAYOUT_SOURCES = import.meta.glob('../../skins/*/components/layout/MainLayout.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

interface SourceBlock {
  start: number
  block: string
}

function lineNumber(source: string, index: number): number {
  return source.slice(0, index).split('\n').length
}

function openingTagBlocks(source: string, pattern: RegExp): SourceBlock[] {
  const blocks: SourceBlock[] = []
  let match: RegExpExecArray | null

  while ((match = pattern.exec(source))) {
    const start = match.index
    const tagClose = source.indexOf('>', start)
    const end = tagClose < 0 ? source.length : tagClose + 1
    blocks.push({ start, block: source.slice(start, end) })
  }

  return blocks
}

function listboxBlocks(source: string): SourceBlock[] {
  return openingTagBlocks(source, /<([A-Za-z][A-Za-z0-9.]*)\b[^>]*role=(["'])listbox\2/g)
}

function listboxTriggerBlocks(source: string): SourceBlock[] {
  return openingTagBlocks(
    source,
    /<button\b[^>]*aria-haspopup=(["'])listbox\1[^>]*>/g,
  )
}

function scriptedButtonBlocks(source: string): SourceBlock[] {
  return openingTagBlocks(
    source,
    /<([a-z][A-Za-z0-9.]*)\b[^>]*role=(["'])button\2/g,
  )
}

describe('layout accessibility source conventions', () => {
  it('covers every skin MainLayout', () => {
    expect(Object.keys(LAYOUT_SOURCES).sort()).toEqual([
      '../../skins/apple/components/layout/MainLayout.tsx',
      '../../skins/carbon/components/layout/MainLayout.tsx',
      '../../skins/ios/components/layout/MainLayout.tsx',
      '../../skins/souwen-google/components/layout/MainLayout.tsx',
      '../../skins/souwen-nebula/components/layout/MainLayout.tsx',
    ])
  })

  it('gives layout listboxes an accessible name', () => {
    const missing = Object.entries(LAYOUT_SOURCES).flatMap(([file, source]) => (
      listboxBlocks(source)
        .filter(({ block }) => !block.includes('aria-label=') && !block.includes('aria-labelledby='))
        .map(({ start }) => `${file}:${lineNumber(source, start)} listbox`)
    )).sort()

    expect(missing).toEqual([])
  })

  it('links listbox disclosure buttons to their controlled listbox', () => {
    const missing = Object.entries(LAYOUT_SOURCES).flatMap(([file, source]) => (
      listboxTriggerBlocks(source)
        .filter(({ block }) => !block.includes('aria-controls='))
        .map(({ start }) => `${file}:${lineNumber(source, start)} listbox trigger`)
    )).sort()

    expect(missing).toEqual([])
  })

  it('uses native buttons instead of scripted layout role=button elements', () => {
    const scripted = Object.entries(LAYOUT_SOURCES).flatMap(([file, source]) => (
      scriptedButtonBlocks(source)
        .map(({ start }) => `${file}:${lineNumber(source, start)} role=button`)
    )).sort()

    expect(scripted).toEqual([])
  })
})
