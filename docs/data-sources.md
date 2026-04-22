# SouWen 数据源清单

**总计**：**84** 个数据源（从 registry 自动生成）。

<!-- BEGIN AUTO -->

## 学术论文 · `paper`（17 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `arxiv` | open_api | 免配置 | search | — |
| `core` | official_api | 需Key | search | `core_api_key` |
| `crossref` | open_api | 免配置 | search | — |
| `dblp` | open_api | 免配置 | search | — |
| `doaj` | official_api | 可选Key | search | `doaj_api_key` |
| `europepmc` | open_api | 免配置 | search | — |
| `hal` | open_api | 免配置 | search | — |
| `huggingface` | open_api | 免配置 | search | — |
| `iacr` | scraper | 免配置 | search | — |
| `openaire` | official_api | 可选Key | search | `openaire_api_key` |
| `openalex` | open_api | 可选Key | search | `openalex_email` |
| `pmc` | open_api | 免配置 | search | — |
| `pubmed` | open_api | 免配置 | search | — |
| `semantic_scholar` | official_api | 可选Key | search | `semantic_scholar_api_key` |
| `unpaywall` | official_api | 可选Key | unpaywall:find_oa | `unpaywall_email` |
| `zenodo` | official_api | 可选Key | search | `zenodo_access_token` |
| `zotero` | official_api | 需Key | search | `zotero_api_key` |

## 专利 · `patent`（8 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `cnipa` | official_api | 需Key | search | `cnipa_client_id` |
| `epo_ops` | official_api | 需Key | search | `epo_consumer_key` |
| `google_patents` | scraper | 免配置 | search | — |
| `patentsview` | open_api | 免配置 | search | — |
| `patsnap` | official_api | 需Key | search | `patsnap_api_key` |
| `pqai` | open_api | 免配置 | search | — |
| `the_lens` | official_api | 需Key | search | `lens_api_token` |
| `uspto_odp` | official_api | 需Key | search | `uspto_api_key` |

## 通用网页搜索 · `web`（28 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `aliyun_iqs` | official_api | 需Key | search | `aliyun_iqs_api_key` |
| `baidu` ⚠️ | scraper | 免配置 | search | — |
| `bing` | scraper | 免配置 | search | — |
| `bing_cn` | scraper | 免配置 | search | — |
| `brave` | scraper | 免配置 | search | — |
| `brave_api` | official_api | 需Key | search | `brave_api_key` |
| `duckduckgo` | scraper | 免配置 | search | — |
| `duckduckgo_images` | scraper | 免配置 | search_images | — |
| `duckduckgo_news` | scraper | 免配置 | search_news | — |
| `duckduckgo_videos` | scraper | 免配置 | search_videos | — |
| `exa` | official_api | 需Key | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | 需Key | fetch, search | `firecrawl_api_key` |
| `google` ⚠️ | scraper | 免配置 | search | — |
| `linkup` | official_api | 需Key | search | `linkup_api_key` |
| `metaso` | official_api | 需Key | search | `metaso_api_key` |
| `mojeek` | scraper | 免配置 | search | — |
| `perplexity` | official_api | 需Key | search | `perplexity_api_key` |
| `scrapingdog` | official_api | 需Key | search | `scrapingdog_api_key` |
| `searxng` | self_hosted | 需自建 | search | `searxng_url` |
| `serpapi` | official_api | 需Key | search | `serpapi_api_key` |
| `serper` | official_api | 需Key | search | `serper_api_key` |
| `startpage` | scraper | 免配置 | search | — |
| `tavily` | official_api | 需Key | fetch, search | `tavily_api_key` |
| `websurfx` | self_hosted | 需自建 | search | `websurfx_url` |
| `whoogle` | self_hosted | 需自建 | search | `whoogle_url` |
| `yahoo` | scraper | 免配置 | search | — |
| `yandex` | scraper | 免配置 | search | — |
| `zhipuai` | official_api | 需Key | search | `zhipuai_api_key` |

## 社交平台 · `social`（5 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `facebook` | official_api | 需Key | search | `facebook_app_id` |
| `reddit` | open_api | 免配置 | search | — |
| `twitter` ⚠️ | official_api | 需Key | search | `twitter_bearer_token` |
| `weibo` | scraper | 免配置 | search | — |
| `zhihu` | scraper | 免配置 | search | — |

## 视频平台 · `video`（2 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `bilibili` | scraper | 可选Key | get_detail, search, search_articles, search_users | `bilibili_sessdata` |
| `youtube` | official_api | 需Key | get_detail, get_transcript, get_trending, search | `youtube_api_key` |

## 百科/知识库 · `knowledge`（1 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `wikipedia` | open_api | 免配置 | search | — |

## 开发者社区 · `developer`（2 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `github` | open_api | 可选Key | search | `github_token` |
| `stackoverflow` | open_api | 可选Key | search | `stackoverflow_api_key` |

## 中文技术社区 · `cn_tech`（3 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `csdn` | scraper | 免配置 | search | — |
| `juejin` | scraper | 免配置 | search | — |
| `linuxdo` | open_api | 免配置 | search | — |

## 企业/办公 · `office`（1 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `feishu_drive` | official_api | 需Key | search | `feishu_app_id` |

## 档案/历史 · `archive`（1 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `wayback` | open_api | 免配置 | archive_lookup, archive_save, fetch | — |

## 内容抓取 · `fetch`（20 源）

| Name | Integration | Key Req | Capabilities | Config Field |
|---|---|---|---|---|
| `apify` | official_api | 需Key | fetch | `apify_api_token` |
| `arxiv_fulltext` | open_api | 免配置 | fetch | — |
| `builtin` | scraper | 免配置 | fetch | — |
| `cloudflare` | official_api | 需Key | fetch | `cloudflare_api_token` |
| `crawl4ai` | scraper | 免配置 | fetch | — |
| `deepwiki` | open_api | 免配置 | fetch | — |
| `diffbot` | official_api | 需Key | fetch | `diffbot_api_token` |
| `exa` | official_api | 需Key | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | 需Key | fetch, search | `firecrawl_api_key` |
| `jina_reader` | open_api | 可选Key | fetch | `jina_api_key` |
| `mcp` | open_api | 免配置 | fetch | — |
| `newspaper` | scraper | 免配置 | fetch | — |
| `readability` | scraper | 免配置 | fetch | — |
| `scraperapi` | official_api | 需Key | fetch | `scraperapi_api_key` |
| `scrapfly` | official_api | 需Key | fetch | `scrapfly_api_key` |
| `scrapingbee` | official_api | 需Key | fetch | `scrapingbee_api_key` |
| `site_crawler` | scraper | 免配置 | fetch | — |
| `tavily` | official_api | 需Key | fetch, search | `tavily_api_key` |
| `wayback` | open_api | 免配置 | archive_lookup, archive_save, fetch | — |
| `zenrows` | official_api | 需Key | fetch | `zenrows_api_key` |

<!-- END AUTO -->

---

## 图例

- ⚠️ high_risk：源易被反爬/限流，默认不启用
- Integration 类型：
  - `open_api` — 公开接口，免 Key
  - `scraper` — 爬虫抓取，需 TLS 伪装
  - `official_api` — 授权接口，需 API Key
  - `self_hosted` — 自托管实例
- Key Req（密钥需求）：
  - 免配置 — 无需任何配置
  - 可选Key — 有 Key 字段但无 Key 也能用
  - 需Key — 必须配置 API Key
  - 需自建 — 需要自建服务实例

## 重新生成

```bash
python tools/gen_docs.py -o docs/data-sources.md
```
