# SouWen 数据源清单

**总计**：**83** 个数据源（从 registry 自动生成）。

<!-- BEGIN AUTO -->

## 学术论文 · `paper`（17 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `arxiv` | open_api | search | — |
| `core` | official_api | search | `core_api_key` |
| `crossref` | open_api | search | — |
| `dblp` | open_api | search | — |
| `doaj` | official_api | search | `doaj_api_key` |
| `europepmc` | open_api | search | — |
| `hal` | open_api | search | — |
| `huggingface` | open_api | search | — |
| `iacr` | scraper | search | — |
| `openaire` | official_api | search | `openaire_api_key` |
| `openalex` | open_api | search | `openalex_email` |
| `pmc` | open_api | search | — |
| `pubmed` | open_api | search | — |
| `semantic_scholar` | official_api | search | `semantic_scholar_api_key` |
| `unpaywall` | official_api | unpaywall:find_oa | `unpaywall_email` |
| `zenodo` | official_api | search | `zenodo_access_token` |
| `zotero` | official_api | search | `zotero_api_key` |

## 专利 · `patent`（8 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `cnipa` | official_api | search | `cnipa_client_id` |
| `epo_ops` | official_api | search | `epo_consumer_key` |
| `google_patents` | scraper | search | — |
| `patentsview` | open_api | search | — |
| `patsnap` | official_api | search | `patsnap_api_key` |
| `pqai` | open_api | search | — |
| `the_lens` | official_api | search | `lens_api_token` |
| `uspto_odp` | official_api | search | `uspto_api_key` |

## 通用网页搜索 · `web`（28 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `aliyun_iqs` | official_api | search | `aliyun_iqs_api_key` |
| `baidu` ⚠️ | scraper | search | — |
| `bing` | scraper | search | — |
| `bing_cn` | scraper | search | — |
| `brave` | scraper | search | — |
| `brave_api` | official_api | search | `brave_api_key` |
| `duckduckgo` | scraper | search | — |
| `duckduckgo_images` | scraper | search_images | — |
| `duckduckgo_news` | scraper | search_news | — |
| `duckduckgo_videos` | scraper | search_videos | — |
| `exa` | official_api | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | fetch, search | `firecrawl_api_key` |
| `google` ⚠️ | scraper | search | — |
| `linkup` | official_api | search | `linkup_api_key` |
| `metaso` | official_api | search | `metaso_api_key` |
| `mojeek` | scraper | search | — |
| `perplexity` | official_api | search | `perplexity_api_key` |
| `scrapingdog` | official_api | search | `scrapingdog_api_key` |
| `searxng` | self_hosted | search | `searxng_url` |
| `serpapi` | official_api | search | `serpapi_api_key` |
| `serper` | official_api | search | `serper_api_key` |
| `startpage` | scraper | search | — |
| `tavily` | official_api | fetch, search | `tavily_api_key` |
| `websurfx` | self_hosted | search | `websurfx_url` |
| `whoogle` | self_hosted | search | `whoogle_url` |
| `yahoo` | scraper | search | — |
| `yandex` | scraper | search | — |
| `zhipuai` | official_api | search | `zhipuai_api_key` |

## 社交平台 · `social`（5 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `facebook` | official_api | search | `facebook_app_id` |
| `reddit` | open_api | search | — |
| `twitter` ⚠️ | official_api | search | `twitter_bearer_token` |
| `weibo` | scraper | search | — |
| `zhihu` | scraper | search | — |

## 视频平台 · `video`（2 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `bilibili` | scraper | get_detail, search, search_articles, search_users | `bilibili_sessdata` |
| `youtube` | official_api | get_detail, get_transcript, get_trending, search | `youtube_api_key` |

## 百科/知识库 · `knowledge`（1 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `wikipedia` | open_api | search | — |

## 开发者社区 · `developer`（2 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `github` | open_api | search | `github_token` |
| `stackoverflow` | open_api | search | `stackoverflow_api_key` |

## 中文技术社区 · `cn_tech`（3 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `csdn` | scraper | search | — |
| `juejin` | scraper | search | — |
| `linuxdo` | open_api | search | — |

## 企业/办公 · `office`（1 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `feishu_drive` | official_api | search | `feishu_app_id` |

## 档案/历史 · `archive`（1 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `wayback` | open_api | archive_lookup, archive_save, fetch | — |

## 内容抓取 · `fetch`（19 源）

| Name | Integration | Capabilities | Config Field |
|---|---|---|---|
| `apify` | official_api | fetch | `apify_api_token` |
| `builtin` | scraper | fetch | — |
| `cloudflare` | official_api | fetch | `cloudflare_api_token` |
| `crawl4ai` | scraper | fetch | — |
| `deepwiki` | open_api | fetch | — |
| `diffbot` | official_api | fetch | `diffbot_api_token` |
| `exa` | official_api | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | fetch, search | `firecrawl_api_key` |
| `jina_reader` | open_api | fetch | `jina_api_key` |
| `mcp` | open_api | fetch | — |
| `newspaper` | scraper | fetch | — |
| `readability` | scraper | fetch | — |
| `scraperapi` | official_api | fetch | `scraperapi_api_key` |
| `scrapfly` | official_api | fetch | `scrapfly_api_key` |
| `scrapingbee` | official_api | fetch | `scrapingbee_api_key` |
| `site_crawler` | scraper | fetch | — |
| `tavily` | official_api | fetch, search | `tavily_api_key` |
| `wayback` | open_api | archive_lookup, archive_save, fetch | — |
| `zenrows` | official_api | fetch | `zenrows_api_key` |

<!-- END AUTO -->

---

## 图例

- ⚠️ high_risk：源易被反爬/限流，默认不启用
- Integration 类型：
  - `open_api` — 公开接口，免 Key
  - `scraper` — 爬虫抓取，需 TLS 伪装
  - `official_api` — 授权接口，需 API Key
  - `self_hosted` — 自托管实例

## 重新生成

```bash
python tools/gen_docs.py -o docs/data-sources.md
```
