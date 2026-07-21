/**
 * Shared renderer for non-paper research outputs.
 *
 * The skin supplies only its existing CSS module classes. This keeps the
 * DataCite-specific distinction between metadata links and downloadable files
 * visible in every skin without coupling core code to a skin module.
 */

import { ExternalLink, FileText, Globe, Scale, Tag, Users } from 'lucide-react'
import type { ResearchOutputResult, ResourceLink } from '../types'

export type ResearchOutputViewMode = 'card' | 'list' | 'grid'

export interface ResearchOutputClassNames {
  card: string
  list: string
  grid: string
  cardHeader: string
  title: string
  sourceBadge: string
  meta: string
  abstract: string
  listTitle: string
  listMeta: string
  gridHeader: string
  gridTitle: string
  gridAbstract: string
  externalIcon?: string
}

export interface ResearchOutputLabels {
  resourceType: string
  rights: string
  access: string
  contentUrls: string
  resources: string
  untitled: string
}

interface ResearchOutputResultViewProps {
  result: ResearchOutputResult
  index: number
  mode: ResearchOutputViewMode
  classes: ResearchOutputClassNames
  labels: ResearchOutputLabels
}

function titleUrl(result: ResearchOutputResult): string | null {
  return result.landing_url || result.source_url || null
}

function resultKey(result: ResearchOutputResult, index: number): string {
  return result.source_record_id || `${result.source}-research-output-${index}`
}

function peopleNames(result: ResearchOutputResult): string {
  return result.creators
    .map((person) => person.name)
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')
}

function resourceType(result: ResearchOutputResult): string {
  return [...new Set([result.resource_type_general, result.resource_type].filter(Boolean))].join(' · ')
}

function rightsText(result: ResearchOutputResult): string {
  return result.rights_list
    .map((right) => right.rights || right.rights_identifier || right.rights_uri || '')
    .filter(Boolean)
    .slice(0, 2)
    .join(' · ')
}

function description(result: ResearchOutputResult): string {
  return result.descriptions
    .map((item) => item.value)
    .filter(Boolean)
    .find(Boolean) ?? ''
}

function linkLabel(resource: ResourceLink): string {
  return resource.label || resource.file_name || resource.relation || resource.url
}

function MetadataLinks({ result, classes, labels }: Pick<ResearchOutputResultViewProps, 'result' | 'classes' | 'labels'>) {
  const contentUrls = [...new Set(result.content_urls.filter(Boolean))]
  const resources = result.resources.filter((resource) => Boolean(resource.url))
  if (contentUrls.length === 0 && resources.length === 0) return null

  return (
    <div className={classes.meta} aria-label={`${labels.contentUrls} ${labels.resources}`}>
      {contentUrls.map((url) => (
        <span key={`content-${url}`}>
          <Globe size={12} /> {labels.contentUrls}:{' '}
          <a href={url} target="_blank" rel="noopener noreferrer">
            {url}
            <ExternalLink size={11} className={classes.externalIcon} />
          </a>
        </span>
      ))}
      {resources.map((resource) => (
        <span key={`resource-${resource.url}`}>
          <FileText size={12} /> {labels.resources}:{' '}
          <a href={resource.url} target="_blank" rel="noopener noreferrer">
            {linkLabel(resource)}
            <ExternalLink size={11} className={classes.externalIcon} />
          </a>
          {resource.format ? ` (${resource.format})` : ''}
        </span>
      ))}
    </div>
  )
}

export function ResearchOutputResultView({
  result,
  index,
  mode,
  classes,
  labels,
}: ResearchOutputResultViewProps) {
  const key = resultKey(result, index)
  const url = titleUrl(result)
  const creators = peopleNames(result)
  const type = resourceType(result)
  const rights = rightsText(result)
  const abstract = description(result)
  const access = result.access?.status
  const title = result.title || result.titles.find(Boolean) || labels.untitled
  const titleNode = url ? (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {title}
      <ExternalLink size={12} className={classes.externalIcon} />
    </a>
  ) : title

  if (mode === 'list') {
    return (
      <div key={key} className={classes.list} data-testid="research-output-result">
        {result.source && <span className={classes.sourceBadge}>{result.source}</span>}
        <span className={classes.listTitle}>{titleNode}</span>
        {type && <span className={classes.listMeta}>— {labels.resourceType}: {type}</span>}
        {creators && <span className={classes.listMeta}>— {creators}</span>}
        {result.publication_year && <span className={classes.listMeta}>— {result.publication_year}</span>}
        {rights && <span className={classes.listMeta}>— {labels.rights}: {rights}</span>}
        {access && <span className={classes.listMeta}>— {labels.access}: {access}</span>}
        <MetadataLinks result={result} classes={classes} labels={labels} />
      </div>
    )
  }

  if (mode === 'grid') {
    const summary = [type, creators, result.publication_year?.toString(), rights].filter(Boolean).join(' · ')
    return (
      <article key={key} className={classes.grid} data-testid="research-output-result">
        <div className={classes.gridHeader}>
          {result.source && <span className={classes.sourceBadge}>{result.source}</span>}
          {type && <span className={classes.meta}>{type}</span>}
        </div>
        <h3 className={classes.gridTitle}>{titleNode}</h3>
        {summary && <p className={classes.gridAbstract}>{summary}</p>}
        <MetadataLinks result={result} classes={classes} labels={labels} />
      </article>
    )
  }

  return (
    <article key={key} className={classes.card} data-testid="research-output-result">
      <div className={classes.cardHeader}>
        <h3 className={classes.title}>{titleNode}</h3>
        {result.source && <span className={classes.sourceBadge}>{result.source}</span>}
      </div>
      <div className={classes.meta}>
        {type && <span><Tag size={12} /> {labels.resourceType}: {type}</span>}
        {creators && <span><Users size={12} /> {creators}</span>}
        {result.publisher && <span>{result.publisher}</span>}
        {result.publication_year && <span>{result.publication_year}</span>}
        {access && <span><Scale size={12} /> {labels.access}: {access}</span>}
      </div>
      {rights && <div className={classes.meta}><span><Scale size={12} /> {labels.rights}: {rights}</span></div>}
      {abstract && <p className={classes.abstract}>{abstract}</p>}
      <MetadataLinks result={result} classes={classes} labels={labels} />
    </article>
  )
}
