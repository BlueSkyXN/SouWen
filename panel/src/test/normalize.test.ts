import { describe, it, expect } from 'vitest'
import { normalizePaper, normalizePatent, normalizeWeb, normalizeDoctor, tierLabel, typeLabel } from '../lib/normalize'

describe('normalizePaper', () => {
  it('extracts author names from Author objects', () => {
    const result = normalizePaper({
      title: 'Test Paper',
      authors: [{ name: 'Alice', affiliation: 'MIT' }, { name: 'Bob' }],
      year: 2024,
      doi: '10.1234/test',
      abstract: 'An abstract',
      source: 'openalex',
      source_url: 'https://example.com',
    } as never)
    expect(result.authors).toEqual(['Alice', 'Bob'])
    expect(result.year).toBe(2024)
    expect(result.url).toBe('https://example.com')
  })

  it('handles string authors gracefully', () => {
    const result = normalizePaper({
      title: 'Old Format',
      authors: ['Alice', 'Bob'],
      year: 2020,
    } as never)
    expect(result.authors).toEqual(['Alice', 'Bob'])
  })

  it('handles missing/null fields', () => {
    const result = normalizePaper({} as never)
    expect(result.title).toBe('')
    expect(result.authors).toEqual([])
    expect(result.year).toBeNull()
    expect(result.doi).toBe('')
    expect(result.url).toBe('')
    expect(result.source).toBe('')
    expect(result.citationCount).toBeNull()
    expect(result.pdfUrl).toBe('')
  })

  it('prefers source_url over open_access_url', () => {
    const result = normalizePaper({
      source_url: 'https://primary.com',
      open_access_url: 'https://fallback.com',
    } as never)
    expect(result.url).toBe('https://primary.com')
  })

  it('falls back to open_access_url', () => {
    const result = normalizePaper({
      open_access_url: 'https://fallback.com',
    } as never)
    expect(result.url).toBe('https://fallback.com')
  })
})

describe('normalizePatent', () => {
  it('extracts fields from backend shape', () => {
    const result = normalizePatent({
      title: 'My Patent',
      patent_id: 'US12345',
      applicants: [{ name: 'CorpA' }, { name: 'CorpB' }],
      inventors: ['Inv1', 'Inv2'],
      abstract: 'Patent abstract',
      source_url: 'https://pat.example.com',
      source: 'patentsview',
      publication_date: '2024-01-15',
    } as never)
    expect(result.patentNumber).toBe('US12345')
    expect(result.applicant).toBe('CorpA, CorpB')
    expect(result.inventors).toEqual(['Inv1', 'Inv2'])
    expect(result.url).toBe('https://pat.example.com')
    expect(result.publicationDate).toBe('2024-01-15')
  })

  it('handles empty applicants', () => {
    const result = normalizePatent({ applicants: [] } as never)
    expect(result.applicant).toBe('')
  })

  it('handles missing fields', () => {
    const result = normalizePatent({} as never)
    expect(result.title).toBe('')
    expect(result.patentNumber).toBe('')
    expect(result.applicant).toBe('')
    expect(result.inventors).toEqual([])
    expect(result.url).toBe('')
  })
})

describe('normalizeWeb', () => {
  it('maps engine to source', () => {
    const result = normalizeWeb({
      title: 'Web Page',
      url: 'https://example.com',
      snippet: 'A snippet',
      engine: 'duckduckgo',
    } as never)
    expect(result.source).toBe('duckduckgo')
    expect(result.snippet).toBe('A snippet')
  })

  it('handles missing engine', () => {
    const result = normalizeWeb({ title: 'X', url: 'u', snippet: 's' } as never)
    expect(result.source).toBe('')
  })
})

describe('normalizeDoctor', () => {
  it('marks reachable when status is ok', () => {
    const result = normalizeDoctor({
      name: 'openalex',
      category: 'paper',
      status: 'ok',
      tier: 0,
      required_key: null,
      message: '',
    })
    expect(result.reachable).toBe(true)
    expect(result.error).toBeNull()
  })

  it('marks unreachable with error message', () => {
    const result = normalizeDoctor({
      name: 'core',
      category: 'paper',
      status: 'error',
      tier: 1,
      required_key: 'CORE_API_KEY',
      message: 'missing key',
    })
    expect(result.reachable).toBe(false)
    expect(result.error).toBe('missing key')
  })
})

describe('tierLabel', () => {
  it('returns Tier N for all values', () => {
    expect(tierLabel(0)).toBe('Tier 0')
    expect(tierLabel(1)).toBe('Tier 1')
    expect(tierLabel(2)).toBe('Tier 2')
    expect(tierLabel(5)).toBe('Tier 5')
  })
})

describe('typeLabel', () => {
  it('returns Chinese labels for known types', () => {
    expect(typeLabel('paper')).toBe('论文')
    expect(typeLabel('patent')).toBe('专利')
    expect(typeLabel('web')).toBe('网页')
  })

  it('returns raw value for unknown types', () => {
    expect(typeLabel('other')).toBe('other')
  })
})
