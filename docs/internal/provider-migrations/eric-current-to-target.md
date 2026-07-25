# ERIC Provider v2 current-to-target mapping and rollback

Status: Phase 5 single-Provider migration record. This document describes the
reviewed canonical projection and rollback boundary; it is not a claim of full
legacy parity, release readiness, deployment, or live ERIC availability.

## Current and target surfaces

| Concern | Current surface | Target surface |
|---|---|---|
| Source declaration | `src/souwen/registry/sources/paper.py` (`eric`) | `ERIC_PROVIDER_MANIFEST` (`eric` / `eric-search`) |
| Client | `souwen.paper.eric.EricClient` | Injected behind `EricSearchProvider` |
| Capability | Legacy `search(query, rows, start)` | Provider SPI `search(SearchRequest, RequestContext, ExecutionContext)` |
| Selection | Legacy registry dispatch | `ProviderManager` plus explicit target provider selection |
| Authentication | Anonymous official API | No secret references |
| Transport configuration | Legacy source channel can resolve `base_url`, proxy, headers, timeout, and retries | Fixed official base URL, no Provider-level proxy or header override; only `enabled`, `timeout_seconds`, and `max_retries` are accepted |

The legacy declaration and client remain present during coexistence. Target
execution must go through `ProviderManager`; the target adapter does not call
another Provider or register another legacy source.

## Canonical request and result mapping

The target adapter accepts only the `paper` domain. It maps the normalized
canonical query unchanged, maps `SearchPageRequest.limit` to ERIC `rows`, and
uses `start=0`. ERIC offset pagination is not exposed as a target cursor in this
slice. A supplied cursor, non-paper or mixed domains, and non-empty canonical
filters fail closed before the client call.

| Legacy normalized value | Canonical DTO value |
|---|---|
| `raw.eric_id` | `SearchItem.id = "eric:<ID>"` and `SearchIdentifier(scheme="eric", value=<ID>)` |
| validated ERIC record URL | `SearchItem.url` |
| `title` | `SearchItem.title` |
| `abstract` | `SearchItem.snippet` |
| `authors[].name` | `SearchAttributes.authors` |
| `year` | `SearchAttributes.year` |
| first `raw.publication_types` value | `SearchAttributes.resource_type` |
| first `raw.language` value | `SearchAttributes.language` |
| `raw.fulltext_authorized` | `SearchAttributes.open_access` for this bounded projection |
| source identity and local rank | `Provenance(provider="eric", ...)` and `SearchItem.rank` |
| `total_results` | `PageInfo.total` |

The adapter deliberately does **not** expose the legacy `journal`, `pdf_url`,
`raw.subjects`, `raw.isbn`, `raw.issn`, `raw.peer_reviewed`, `raw.publisher`,
`raw.citation`, `raw.external_url`, or arbitrary upstream/raw payload fields.
It also does not expose legacy offset pagination, upstream ordering guarantees,
or a continuation cursor. Dropping these fields is an intentional canonical
boundary, not proof that the target response is field-for-field equivalent to
the legacy response. The `open_access` projection records the legacy boolean
only; it does not establish a license, rights grant, or redistribution permission.

## Default selection, coexistence, and rollback

- OpenAlex remains the default target `paper` Search Provider. ERIC is not a
  default fallback and is reached only by explicit target provider selection.
- ERIC is not part of target runtime required readiness. Its absence or disabled
  state must not make OpenAlex, builtin Fetch, or the overall required Provider
  readiness fail.
- Set `sources.eric.enabled: false` and reload/rebuild the target runtime to make
  the ERIC target manifest ineligible. Read back the target Provider catalog and
  verify that ERIC is unavailable, then verify that an omitted-provider paper
  search still selects OpenAlex.
- `sources.eric.enabled: false` is an eligibility rollback, not an automatic
  route-to-legacy switch. Because the legacy and target declarations share the
  `eric` source name, operators must not claim that this flag preserves legacy
  ERIC dispatch. A code/deployment rollback uses the prior known-good candidate
  while the legacy declaration and client remain in the source tree.
- Do not remove the legacy declaration, change OpenAlex priority, or add ERIC to
  required readiness as part of this slice.

## Deterministic evidence boundary

The `provider_v2_conformance` V2 CI job covers the SPI, manifest registry,
Provider Manager, existing OpenAlex/builtin Fetch/UniAPI adapters, the ERIC
legacy characterization, and ERIC Provider v2 conformance. It uses repository
fixtures and fakes only: no network, browser runtime, or secret is required.

Passing that job proves deterministic contract conformance for the checked
candidate. It does not prove live ERIC behavior, complete legacy parity,
deployment, release publication, or runtime promotion.
