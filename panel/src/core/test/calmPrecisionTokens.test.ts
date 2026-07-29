import { describe, expect, it } from 'vitest'
import { compile } from 'sass-embedded'

declare const process: { cwd: () => string }

const tokenFile = `${process.cwd()}/src/core/styles/calm-precision.scss`
const calmPrecisionSource = compile(tokenFile).css

function channel(value: number) {
  const normalized = value / 255
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4
}

function luminance(value: string) {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(value)
  if (!match) throw new Error(`Expected a six-digit hex color, received ${value}`)
  const [, red, green, blue] = match
  return 0.2126 * channel(Number.parseInt(red, 16))
    + 0.7152 * channel(Number.parseInt(green, 16))
    + 0.0722 * channel(Number.parseInt(blue, 16))
}

function contrast(foreground: string, background: string) {
  const [lighter, darker] = [luminance(foreground), luminance(background)]
    .sort((left, right) => right - left)
  return (lighter + 0.05) / (darker + 0.05)
}

function block(selector: string) {
  const start = calmPrecisionSource.indexOf(selector)
  if (start < 0) throw new Error(`Missing ${selector} token block`)
  const open = calmPrecisionSource.indexOf('{', start)
  let depth = 0
  for (let index = open; index < calmPrecisionSource.length; index += 1) {
    if (calmPrecisionSource[index] === '{') depth += 1
    if (calmPrecisionSource[index] === '}') depth -= 1
    if (depth === 0) return calmPrecisionSource.slice(open + 1, index)
  }
  throw new Error(`Unclosed ${selector} token block`)
}

function colorTokens(selector: string) {
  const tokens: Record<string, string> = {}
  for (const line of block(selector).split('\n')) {
    const match = /^\s*(--cp-[\w-]+):\s*(#[0-9a-f]{6});\s*$/i.exec(line)
    if (match) tokens[match[1]] = match[2].toLowerCase()
  }
  return tokens
}

const lightTokens = colorTokens(':root')
const darkTokens = { ...lightTokens, ...colorTokens(':root[data-mode=dark]') }

describe('Calm Precision color tokens', () => {
  for (const mode of ['light', 'dark'] as const) {
    it(`${mode} mode keeps text, controls and semantic states above their contrast gates`, () => {
      const tokens = mode === 'dark' ? darkTokens : lightTokens
      const token = (name: string) => tokens[name] ?? ''

      const backgrounds = ['--cp-canvas', '--cp-surface', '--cp-raised']
      for (const foreground of ['--cp-text', '--cp-text-muted', '--cp-text-tertiary']) {
        for (const background of backgrounds) {
          expect(
            contrast(token(foreground), token(background)),
            `${foreground} on ${background}`,
          ).toBeGreaterThanOrEqual(4.5)
        }
      }

      for (const background of ['--cp-canvas', '--cp-raised']) {
        expect(
          contrast(token('--cp-border-control'), token(background)),
          `--cp-border-control on ${background}`,
        ).toBeGreaterThanOrEqual(3)
        expect(
          contrast(token('--cp-focus'), token(background)),
          `--cp-focus on ${background}`,
        ).toBeGreaterThanOrEqual(3)
      }

      expect(contrast(token('--cp-on-primary'), token('--cp-primary'))).toBeGreaterThanOrEqual(4.5)
      expect(contrast(token('--cp-on-accent'), token('--cp-accent'))).toBeGreaterThanOrEqual(4.5)

      for (const status of ['critical', 'success', 'warning', 'info']) {
        expect(
          contrast(token(`--cp-${status}`), token(`--cp-${status}-soft`)),
          `--cp-${status} on --cp-${status}-soft`,
        ).toBeGreaterThanOrEqual(4.5)
      }
    })
  }
})
