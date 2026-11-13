# SouWen Provider v2 数据源清单

本页由每个内置 Provider package 的 `manifest.py` 经 `souwen.providers.catalog.builtin_provider_manifests()` 生成。Manifest Registry 与 Provider Manager 是唯一运行时事实来源；不存在并行的旧 source registry。

公开能力严格只有 `search`、`llm_search`、`fetch`。同一 package 可以提供多个能力，每个能力对应一个明确 adapter；列表不包含已退休的 citation、detail、archive-save、recursive-crawl 或 browser-fetch 产品入口。

## 摘要

| 指标 | 数量 |
|---|---:|
| Provider packages | **36** |
| Provider adapters | **36** |
| Search packages | **32** |
| LLM Search packages | **0** |
| Fetch packages | **4** |

## 内置 Provider packages

| Provider | Capabilities | Availability | Auth references | Network contract | Browser | Costed |
|---|---|---|---|---|---:|---:|
| `arxiv` | `search` | `search:configured` | none | `export.arxiv.org` | no | no |
| `arxiv_fulltext` | `fetch` | `fetch:configured` | none | `arxiv.org` | no | no |
| `baidu` | `search` | `search:configured` | none | `www.baidu.com` | no | no |
| `brave` | `search` | `search:configured` | none | `search.brave.com` | no | no |
| `builtin-fetch` | `fetch` | `fetch:always` | none | none | no | no |
| `coolapk` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `crossref` | `search` | `search:configured` | none | `api.crossref.org` | no | no |
| `datacite` | `search` | `search:configured` | none | `api.datacite.org` | no | no |
| `doaj` | `search` | `search:always` | optional: `DOAJ_API_KEY` | `doaj.org` | no | no |
| `duckduckgo_news` | `search` | `search:configured` | none | `duckduckgo.com` | no | no |
| `epo_ops` | `search` | `search:configured` | required: `EPO_CONSUMER_KEY`, `EPO_CONSUMER_SECRET` | `ops.epo.org` | no | no |
| `eric` | `search` | `search:configured` | none | `api.ies.ed.gov` | no | no |
| `europepmc` | `search` | `search:configured` | none | `www.ebi.ac.uk` | no | no |
| `figshare` | `search` | `search:configured` | none | `api.figshare.com` | no | no |
| `github` | `search` | `search:always` | optional: `GITHUB_TOKEN` | `api.github.com` | no | no |
| `hal` | `search` | `search:configured` | none | `api.archives-ouvertes.fr` | no | no |
| `huggingface` | `search` | `search:configured` | none | `huggingface.co` | no | no |
| `iacr` | `search` | `search:configured` | none | `eprint.iacr.org` | no | no |
| `internet_archive` | `search` | `search:configured` | none | `archive.org` | no | no |
| `jina_reader` | `fetch` | `fetch:always` | optional: `JINA_API_KEY` | `r.jina.ai` | no | no |
| `juejin` | `search` | `search:configured` | none | `api.juejin.cn` | no | no |
| `library_of_congress` | `search` | `search:configured` | none | `www.loc.gov` | no | no |
| `open_library` | `search` | `search:configured` | none | `openlibrary.org` | no | no |
| `openaire` | `search` | `search:always` | optional: `OPENAIRE_API_KEY` | `api.openaire.eu` | no | no |
| `openalex` | `search` | `search:configured` | none | `api.openalex.org` | no | no |
| `osti` | `search` | `search:configured` | none | `www.osti.gov` | no | no |
| `patentsview` | `search` | `search:configured` | required: `PATENTSVIEW_API_KEY` | `search.patentsview.org` | no | no |
| `pubmed` | `search` | `search:configured` | optional: `PUBMED_API_KEY` | `eutils.ncbi.nlm.nih.gov` | no | no |
| `searxng` | `search` | `search:configured` | none | `configured_self_hosted_endpoint` | no | no |
| `stackoverflow` | `search` | `search:always` | optional: `STACKOVERFLOW_API_KEY` | `api.stackexchange.com` | no | no |
| `uspto_odp` | `search` | `search:configured` | required: `USPTO_API_KEY` | `data.uspto.gov` | no | no |
| `wayback` | `fetch` | `fetch:always` | none | `archive.org`, `web.archive.org` | no | no |
| `wikipedia` | `search` | `search:always` | none | `zh.wikipedia.org` | no | no |
| `yahoo` | `search` | `search:configured` | none | `search.yahoo.com` | no | no |
| `youtube` | `search` | `search:configured` | required: `YOUTUBE_API_KEY` | `www.googleapis.com` | no | no |
| `zenodo` | `search` | `search:always` | optional: `ZENODO_ACCESS_TOKEN` | `zenodo.org` | no | no |

## 重新生成与校验

```bash
PYTHONPATH=src python3 tools/gen_docs.py --write
PYTHONPATH=src python3 tools/gen_docs.py --check
```
