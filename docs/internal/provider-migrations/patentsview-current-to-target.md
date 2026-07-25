# PatentsView Provider v2 current-to-target mapping and rollback

Status: Phase 5 single-Provider migration record. This is a bounded canonical
projection and coexistence contract, not a claim of complete legacy parity,
live credential validity, deployment, or release readiness.

## Runtime and configuration boundary

| Concern | Current surface | Target surface |
|---|---|---|
| Declaration | Legacy `patentsview` registry source | `PATENTSVIEW_PROVIDER_MANIFEST` / `patentsview-search` |
| Client | `PatentsViewClient` resolves global/source config | Explicit transport injected by the composition root |
| Secret | `patentsview_api_key` / source `api_key` | Resolved reference `PATENTSVIEW_API_KEY`; value never enters catalog or diagnostics |
| Network | Legacy source channel may resolve transport overrides | Fixed `https://search.patentsview.org/api/v1`, no Provider-level proxy/base URL/header override |
| Edition | Legacy minimum edition `pro` | Coexistence runtime derives the same gate from the legacy source policy |
| Selection | Not a legacy default patent source | Target explicit selection only; it is not registered as a patent default |

Target eligibility requires the `pro` or `full` edition, explicit
`sources.patentsview.enabled: true`, and a resolved API key. Missing credentials
produce a safe `unavailable/missing_configuration` catalog item naming only
`patentsview_api_key`. PatentsView is optional and is not part of required
readiness.

## Canonical request and result mapping

The target adapter accepts only the `patent` domain, first-page requests, and
no non-empty canonical filters. It converts the canonical query to the fixed
legacy-compatible title query:

```python
{"_contains": {"patent_title": request.query}}
```

It does not expose the PatentsView JSON DSL, caller-selected fields, sort,
numbered pages, convenience methods, or an invented continuation cursor.

| Legacy normalized value | Canonical DTO value |
|---|---|
| `patent_id` | `SearchItem.id = "patentsview:<ID>"` and `SearchIdentifier(scheme="patentsview", ...)` |
| validated record URL | rebuilt `SearchItem.url` |
| `title` | required `SearchItem.title` |
| `abstract` | optional `SearchItem.snippet` |
| `publication_date.year` | `SearchAttributes.year` |
| patent domain | `SearchAttributes.resource_type = "patent"` |
| local rank/source | `SearchItem.rank` and PatentsView provenance |
| `total_results` | `PageInfo.total` |

This slice deliberately does not expose `application_number`, filing date,
applicants, inventors, IPC/CPC codes, claims, family ID, legal status, PDF URL,
or arbitrary raw fields. Inventors are not relabeled as generic `authors`.
Future patent-specific metadata requires an additive canonical contract rather
than raw payload leakage.

## Coexistence and rollback

- The legacy registry declaration and client remain in place as rollback truth.
- Target requests execute only through `ProviderManager`; there is no target to
  legacy double dispatch.
- Disabling `sources.patentsview.enabled` removes target eligibility. It does
  not silently route the request to the legacy dispatcher.
- Operational rollback uses the prior known-good candidate. Removing the
  legacy declaration or changing patent defaults is outside this slice.

The deterministic Provider v2 conformance job uses fake transports and secret
canaries only. It proves checked contract behavior, not the validity of a real
PatentsView account, quota, price, live endpoint, deployment, or publication.
