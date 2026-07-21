# SouWen 数据源指南与清单

## Registry 指标

| 指标 | 数量 | 定义 |
|---|---:|---|
| Registered | **108** | 当前生成进程注册的 `SourceAdapter`；默认只含内置源 |
| Public | **107** | `catalog_visibility=public`，进入公开 Source Catalog |
| Hidden / internal | **1** | 已注册但不进入公开 Source Catalog |
| Fetch primary-domain | **17** | 主 `domain=fetch` 的公开源 |
| Fetch cross-domain | **7** | 其他主 domain 通过 `extra_domains` 暴露 `fetch` |
| Fetch providers | **24** | primary-domain 与 cross-domain 的公开源并集 |

## 事实来源

本页不是手工维护的静态表，而是由 `src/souwen/registry/sources/` 中的 `SourceAdapter` 声明投影为正式 Source Catalog 后，经 `tools/gen_docs.py` 生成。`SourceAdapter` 同时驱动 CLI、REST API、doctor、Panel 和插件视图。

默认生成只包含内置源，并显式关闭外部插件自动加载；这样即使本机安装了 `souwen.plugins` entry point，checked-in 文档也能稳定复现。需要把本机插件一并展示时再使用 `--include-plugins`。

## 如何阅读

- 本页主表按 registry domain 展示：`paper` / `patent` / `web` / `social` / `video` / `knowledge` / `developer` / `cn_tech` / `office` / `archive` / `fetch`。
- 正式 Source Catalog 使用展示分类：`book`（图书/馆藏） / `paper`（学术论文） / `research_output`（科研产出） / `patent`（专利） / `web_general`（通用网页搜索） / `web_professional`（专业网页搜索） / `social`（社交平台） / `office`（企业/办公） / `developer`（开发者社区） / `knowledge`（百科/知识库） / `cn_tech`（中文技术社区） / `video`（视频平台） / `archive`（档案/历史） / `fetch`（内容抓取）。
- `/api/v1/sources`、CLI 和 Panel 使用同一份公开 Source Catalog：`sources[]` 保留全部公开条目，并用 `category`、`domain`、`capabilities`、`available` 描述 edition、启用状态和凭据形成的静态 policy/config readiness；`runtime_available` / `runtime_reason` 独立描述本地依赖 importability。
- `Capabilities` 是门面层可派发能力；`fetch` 既可以属于主 domain，也可以由其他主 domain 源通过 `extra_domains` 声明为跨域能力。具体名单和计数均从 registry 派生。

## 配置口径

- Auth 的取值是 `none` / `optional` / `required` / `self_hosted`。`optional` 表示缺凭据仍可用，但配置后可提升限流、配额、质量或登录态能力；`required` 与 `self_hosted` 缺少声明字段时仍保留 catalog 条目，并以 `available=false` 标记。
- `Credentials` 列出完整字段；多字段源必须全部满足。频道级 `sources.<name>.api_key` 只覆盖主 `config_field`，其余字段仍读取 flat config。
- 自建实例源读取 `sources.<name>.base_url`；当前内置自建源为 `searxng`、`whoogle`、`websurfx`。
- `Risk` 只描述默认调度风险，不等同于接入方式；`Distribution` 描述推荐安装/治理边界；`Extra` 是推荐安装的 optional dependency 组。

## 运行时可见性

`/api/v1/sources` 会从 live registry 派生公开 catalog，禁用源、缺必需凭据源和缺自建实例地址的源仍会保留条目，但 `available=false`；doctor 和管理端 `/api/v1/admin/sources/config` 会展示所有注册源及其状态、凭据字段、频道配置和 catalog 元数据。

`stability` 是 registry 声明的接入成熟度，不是实时连通性承诺；`/api/v1/sources[].available` 只表示当前 edition、启用状态和凭据条件满足，不证明 optional runtime dependency 可导入，也不证明上游此刻可达。Catalog 和 doctor 的 `runtime_available` / `runtime_reason` 独立报告依赖/importability；默认 `live=false`，只有显式 live probe 的结果才描述当次联网观测。

<!-- BEGIN AUTO -->

## 学术论文 · `paper`（21 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `arxiv` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `biorxiv` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `core` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `core_api_key` |
| `crossref` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `dblp` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `doaj` | official_api | 可选凭据 (提升限流) | 低风险 | 核心内置 | 稳定 | — | search | `doaj_api_key` |
| `eric` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `europepmc` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `hal` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `huggingface` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `iacr` | scraper | 免配置 | 中风险 | 可选依赖 | 实验性 | `scraper` | search | — |
| `ieee_xplore` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `ieee_api_key` |
| `openaire` | official_api | 可选凭据 (提升配额) | 低风险 | 核心内置 | 稳定 | — | search | `openaire_api_key` |
| `openalex` | open_api | 可选凭据 (提升配额) | 低风险 | 核心内置 | 稳定 | — | search | `openalex_api_key` |
| `opencitations` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | opencitations:citation_count, opencitations:citations, opencitations:references | — |
| `osti` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |
| `pmc` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `pubmed` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `semantic_scholar` | official_api | 可选凭据 (提升限流) | 低风险 | 核心内置 | 稳定 | — | search | `semantic_scholar_api_key` |
| `zenodo` | official_api | 可选凭据 (提升配额) | 低风险 | 核心内置 | 稳定 | — | search | `zenodo_access_token` |
| `zotero` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `zotero_api_key`, `zotero_library_id` |

## 专利 · `patent`（8 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `cnipa` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `cnipa_client_id`, `cnipa_client_secret` |
| `epo_ops` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `epo_consumer_key`, `epo_consumer_secret` |
| `google_patents` | scraper | 免配置 | 中风险 | 可选依赖 | 实验性 | `scraper` | search | — |
| `patentsview` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `patentsview_api_key` |
| `patsnap` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `patsnap_api_key` |
| `pqai` | open_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `pqai_api_token` |
| `the_lens` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `lens_api_token` |
| `uspto_odp` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `uspto_api_key` |

## 通用网页搜索 · `web`（32 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `aliyun_iqs` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `aliyun_iqs_api_key` |
| `baidu` ⚠️ | scraper | 免配置 | 高风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `bing` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `bing_cn` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `brave` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `brave_api` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `brave_api_key` |
| `duckduckgo` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `duckduckgo_images` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search_images | — |
| `duckduckgo_news` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search_news | — |
| `duckduckgo_videos` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search_videos | — |
| `exa` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `firecrawl_api_key` |
| `google` ⚠️ | scraper | 免配置 | 高风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `kimi_code` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `kimi_code_api_key` |
| `linkup` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `linkup_api_key` |
| `metaso` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `metaso_api_key` |
| `mojeek` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `perplexity` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `perplexity_api_key` |
| `scrapingdog` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `scrapingdog_api_key` |
| `searxng` | self_hosted | 自建实例 | 低风险 | 核心内置 | 稳定 | — | search | `searxng_url` |
| `serpapi` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `serpapi_api_key` |
| `serper` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `serper_api_key` |
| `startpage` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `tavily` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `tavily_api_key` |
| `uniapi_ark_annotations_deepseek_v3_2_251201` | official_api | 必须凭据 | 中风险 | 核心内置 | 实验性 | — | search | `llm_search_gateways.uniapi.api_key`, `llm_search_gateways.uniapi.base_url` |
| `uniapi_ark_annotations_doubao_seed_2_0_lite_260428` | official_api | 必须凭据 | 中风险 | 核心内置 | 实验性 | — | search | `llm_search_gateways.uniapi.api_key`, `llm_search_gateways.uniapi.base_url` |
| `websurfx` | self_hosted | 自建实例 | 低风险 | 核心内置 | 稳定 | — | search | `websurfx_url` |
| `whoogle` | self_hosted | 自建实例 | 低风险 | 核心内置 | 稳定 | — | search | `whoogle_url` |
| `xcrawl` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `xcrawl_api_key` |
| `yahoo` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `yandex` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `zhipuai` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `zhipuai_api_key` |

## 社交平台 · `social`（5 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `facebook` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `facebook_app_id`, `facebook_app_secret` |
| `reddit` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `twitter` ⚠️ | official_api | 必须凭据 | 高风险 | 核心内置 | 稳定 | — | search | `twitter_bearer_token` |
| `weibo` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `zhihu` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |

## 视频平台 · `video`（2 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `bilibili` | scraper | 可选凭据 (个性化/登录态增强) | 低风险 | 可选依赖 | 稳定 | `scraper` | get_detail, search, search_articles, search_users | `bilibili_sessdata` |
| `youtube` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | get_detail, get_transcript, get_trending, search | `youtube_api_key` |

## 百科/知识库 · `knowledge`（1 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `wikipedia` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |

## 开发者社区 · `developer`（2 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `github` | open_api | 可选凭据 (提升限流) | 低风险 | 核心内置 | 稳定 | — | search | `github_token` |
| `stackoverflow` | open_api | 可选凭据 (提升配额) | 低风险 | 核心内置 | 稳定 | — | search | `stackoverflow_api_key` |

## 中文技术社区 · `cn_tech`（9 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `community_cn` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `coolapk` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `csdn` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `hostloc` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `juejin` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `linuxdo` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |
| `nodeseek` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `v2ex` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |
| `xiaohongshu` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | search | — |

## 企业/办公 · `office`（1 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `feishu_drive` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | search | `feishu_app_id`, `feishu_app_secret` |

## 档案/历史 · `archive`（1 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `wayback` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | archive_lookup, archive_save, fetch | — |

## 内容抓取 · `fetch`（24 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `apify` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `apify_api_token` |
| `arxiv_fulltext` | open_api | 免配置 | 低风险 | 可选依赖 | 稳定 | `pdf` | fetch | — |
| `builtin` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `web` | fetch | — |
| `cloudflare` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `cloudflare_api_token`, `cloudflare_account_id` |
| `crawl4ai` | scraper | 免配置 | 中风险 | 可选依赖 | 稳定 | `crawl4ai` | fetch | — |
| `deepwiki` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | fetch | — |
| `diffbot` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `diffbot_api_token` |
| `exa` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | exa:find_similar, fetch, search | `exa_api_key` |
| `firecrawl` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `firecrawl_api_key` |
| `jina_reader` | open_api | 可选凭据 (提升限流) | 低风险 | 核心内置 | 稳定 | — | fetch | `jina_api_key` |
| `kimi_code` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `kimi_code_api_key` |
| `mcp` | open_api | 自建实例 | 低风险 | 可选依赖 | 稳定 | `mcp` | fetch | `mcp_server_url` |
| `metaso` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `metaso_api_key` |
| `newspaper` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `newspaper` | fetch | — |
| `readability` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `readability` | fetch | — |
| `scraperapi` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `scraperapi_api_key` |
| `scrapfly` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `scrapfly_api_key` |
| `scrapingbee` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `scrapingbee_api_key` |
| `scrapling` | scraper | 免配置 | 中风险 | 可选依赖 | 稳定 | `scrapling` | fetch | — |
| `site_crawler` | scraper | 免配置 | 低风险 | 可选依赖 | 稳定 | `scraper` | fetch | — |
| `tavily` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `tavily_api_key` |
| `wayback` | open_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | archive_lookup, archive_save, fetch | — |
| `xcrawl` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch, search | `xcrawl_api_key` |
| `zenrows` | official_api | 必须凭据 | 低风险 | 核心内置 | 稳定 | — | fetch | `zenrows_api_key` |

## book · `book`（7 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `doab` | official_api | 免配置 | 低风险 | 核心内置 | 实验性 | — | get_detail, search | — |
| `internet_archive` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |
| `library_of_congress` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |
| `librivox` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |
| `oapen` | official_api | 免配置 | 低风险 | 核心内置 | 实验性 | — | get_detail, search | — |
| `open_library` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |
| `wikisource` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | get_detail, search | — |

## research_output · `research_output`（1 源）

| Name | Integration | Auth | Risk | Distribution | Stability | Extra | Capabilities | Credentials |
|---|---|---|---|---|---|---|---|---|
| `datacite` | official_api | 免配置 | 低风险 | 核心内置 | 稳定 | — | search | — |

<!-- END AUTO -->

---

## 图例

- ⚠️ high_risk：高风险源，等价于 `risk_level=high`。
- Integration 描述接入方式：`open_api` / `scraper` / `official_api` / `self_hosted`。
- Auth 描述运行前配置要求：免配置 / 可选凭据 / 必须凭据 / 自建实例。
- Risk 描述默认调度风险，不等同于 Integration。
- Distribution 描述推荐治理/安装范围：核心内置 / 可选依赖 / 外部插件。
- Extra 表示建议安装的 optional dependency 组。
- Stability 描述声明式接入成熟度：稳定 / Beta / 实验性 / 已弃用；不等于实时可用性或可达性。

## 重新生成与校验

```bash
PYTHONPATH=src python3 tools/gen_docs.py --write
PYTHONPATH=src python3 tools/gen_docs.py --check
```

如需在本机 catalog 中展示已安装的外部插件，可追加 `--include-plugins`。
