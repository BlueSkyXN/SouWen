# SouWen Provider v2 数据源清单

本页由每个内置 Provider package 的 `manifest.py` 经 `souwen.providers.catalog.builtin_provider_manifests()` 生成。Manifest Registry 与 Provider Manager 是唯一运行时事实来源；不存在并行的旧 source registry。

公开能力严格只有 `search`、`llm_search`、`fetch`。同一 package 可以提供多个能力，每个能力对应一个明确 adapter；列表不包含已退休的 citation、detail、archive-save、recursive-crawl 或 browser-fetch 产品入口。

## 摘要

| 指标 | 数量 |
|---|---:|
| Provider packages | **71** |
| Provider adapters | **71** |
| Search packages | **64** |
| LLM Search packages | **0** |
| Fetch packages | **7** |

## 内置 Provider packages

| Provider | Capabilities | Availability | Auth references | Network contract | Browser | Costed |
|---|---|---|---|---|---:|---:|
| `arxiv` | `search` | `search:configured` | none | `export.arxiv.org` | no | no |
| `arxiv_fulltext` | `fetch` | `fetch:configured` | none | `arxiv.org` | no | no |
| `baidu` | `search` | `search:configured` | none | `www.baidu.com` | no | no |
| `bilibili` | `search` | `search:configured` | optional: `BILIBILI_SESSDATA` | `api.bilibili.com` | no | no |
| `bing` | `search` | `search:configured` | none | `www.bing.com` | no | no |
| `bing_cn` | `search` | `search:configured` | none | `cn.bing.com` | no | no |
| `biorxiv` | `search` | `search:configured` | none | `api.biorxiv.org` | no | no |
| `brave` | `search` | `search:configured` | none | `search.brave.com` | no | no |
| `builtin-fetch` | `fetch` | `fetch:always` | none | none | no | no |
| `coolapk` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `crossref` | `search` | `search:configured` | none | `api.crossref.org` | no | no |
| `csdn` | `search` | `search:configured` | none | `so.csdn.net` | no | no |
| `datacite` | `search` | `search:configured` | none | `api.datacite.org` | no | no |
| `dblp` | `search` | `search:configured` | none | `dblp.org` | no | no |
| `deepwiki` | `fetch` | `fetch:always` | optional: `JINA_API_KEY` | `deepwiki.com`, `r.jina.ai` | no | no |
| `doab` | `search` | `search:configured` | none | `directory.doabooks.org` | no | no |
| `doaj` | `search` | `search:always` | optional: `DOAJ_API_KEY` | `doaj.org` | no | no |
| `duckduckgo` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `duckduckgo_images` | `search` | `search:configured` | none | `duckduckgo.com` | no | no |
| `duckduckgo_news` | `search` | `search:configured` | none | `duckduckgo.com` | no | no |
| `duckduckgo_videos` | `search` | `search:configured` | none | `duckduckgo.com` | no | no |
| `epo_ops` | `search` | `search:configured` | required: `EPO_CONSUMER_KEY`, `EPO_CONSUMER_SECRET` | `ops.epo.org` | no | no |
| `eric` | `search` | `search:configured` | none | `api.ies.ed.gov` | no | no |
| `europepmc` | `search` | `search:configured` | none | `www.ebi.ac.uk` | no | no |
| `figshare` | `search` | `search:configured` | none | `api.figshare.com` | no | no |
| `github` | `search` | `search:always` | optional: `GITHUB_TOKEN` | `api.github.com` | no | no |
| `google` | `search` | `search:configured` | none | `www.google.com` | no | no |
| `google_patents` | `search` | `search:configured` | none | `patents.google.com` | no | no |
| `gutenberg` | `search` | `search:configured` | none | none | no | no |
| `hal` | `search` | `search:configured` | none | `api.archives-ouvertes.fr` | no | no |
| `hostloc` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `huggingface` | `search` | `search:configured` | none | `huggingface.co` | no | no |
| `iacr` | `search` | `search:configured` | none | `eprint.iacr.org` | no | no |
| `internet_archive` | `search` | `search:configured` | none | `archive.org` | no | no |
| `jina_reader` | `fetch` | `fetch:always` | optional: `JINA_API_KEY` | `r.jina.ai` | no | no |
| `juejin` | `search` | `search:configured` | none | `api.juejin.cn` | no | no |
| `library_of_congress` | `search` | `search:configured` | none | `www.loc.gov` | no | no |
| `librivox` | `search` | `search:configured` | none | `librivox.org` | no | no |
| `linuxdo` | `search` | `search:always` | none | `linux.do` | no | no |
| `mojeek` | `search` | `search:configured` | none | `www.mojeek.com` | no | no |
| `newspaper` | `fetch` | `fetch:configured` | none | `validated_public_target` | no | no |
| `nodeseek` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `oapen` | `search` | `search:configured` | none | `library.oapen.org` | no | no |
| `open_library` | `search` | `search:configured` | none | `openlibrary.org` | no | no |
| `openaire` | `search` | `search:always` | optional: `OPENAIRE_API_KEY` | `api.openaire.eu` | no | no |
| `openalex` | `search` | `search:configured` | none | `api.openalex.org` | no | no |
| `osti` | `search` | `search:configured` | none | `www.osti.gov` | no | no |
| `patentsview` | `search` | `search:configured` | required: `PATENTSVIEW_API_KEY` | `search.patentsview.org` | no | no |
| `pmc` | `search` | `search:configured` | optional: `PUBMED_API_KEY` | `eutils.ncbi.nlm.nih.gov` | no | no |
| `pubmed` | `search` | `search:configured` | optional: `PUBMED_API_KEY` | `eutils.ncbi.nlm.nih.gov` | no | no |
| `readability` | `fetch` | `fetch:configured` | none | `validated_public_target` | no | no |
| `reddit` | `search` | `search:always` | optional: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | `www.reddit.com`, `oauth.reddit.com` | no | no |
| `searxng` | `search` | `search:configured` | none | `configured_self_hosted_endpoint` | no | no |
| `semantic_scholar` | `search` | `search:always` | optional: `SEMANTIC_SCHOLAR_API_KEY` | `api.semanticscholar.org` | no | no |
| `stackoverflow` | `search` | `search:always` | optional: `STACKOVERFLOW_API_KEY` | `api.stackexchange.com` | no | no |
| `startpage` | `search` | `search:configured` | none | `www.startpage.com` | no | no |
| `taiwan_new_books` | `search` | `search:configured` | none | none | no | no |
| `uspto_odp` | `search` | `search:configured` | required: `USPTO_API_KEY` | `data.uspto.gov` | no | no |
| `v2ex` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `wayback` | `fetch` | `fetch:always` | none | `archive.org`, `web.archive.org` | no | no |
| `websurfx` | `search` | `search:configured` | none | `configured_self_hosted_endpoint` | no | no |
| `weibo` | `search` | `search:configured` | none | `m.weibo.cn` | no | no |
| `whoogle` | `search` | `search:configured` | none | `configured_self_hosted_endpoint` | no | no |
| `wikipedia` | `search` | `search:always` | none | `zh.wikipedia.org` | no | no |
| `wikisource` | `search` | `search:configured` | none | `zh.wikisource.org` | no | no |
| `xiaohongshu` | `search` | `search:configured` | none | `html.duckduckgo.com` | no | no |
| `yahoo` | `search` | `search:configured` | none | `search.yahoo.com` | no | no |
| `yandex` | `search` | `search:configured` | none | `yandex.com` | no | no |
| `youtube` | `search` | `search:configured` | required: `YOUTUBE_API_KEY` | `www.googleapis.com` | no | no |
| `zenodo` | `search` | `search:always` | optional: `ZENODO_ACCESS_TOKEN` | `zenodo.org` | no | no |
| `zhihu` | `search` | `search:configured` | none | `www.zhihu.com` | no | no |

## 重新生成与校验

```bash
PYTHONPATH=src python3 tools/gen_docs.py --write
PYTHONPATH=src python3 tools/gen_docs.py --check
```
