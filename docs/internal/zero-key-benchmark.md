# 无 API Key 场景实测报告

> **测试环境**: Hugging Face Spaces Docker 部署
> **SouWen 版本**: v1.1.1（远程 `/openapi.json`）
> **测试时间**: 2026-05-02
> **部署地址**: https://blueskyxn-souwen.hf.space/
> **测试查询**: 主要使用 `machine learning`；Google Patents 另以 `artificial intelligence`、`semiconductor` 复核
> **测试前后状态**: 测试前 `default_http_backend=auto`、WARP 关闭；测试结束后已恢复为 `default_http_backend=auto`、WARP 关闭

## 概述

本文档记录远程 HF Spaces 部署在无搜索 API Key 场景下的真实表现。与 2026-04-18 的旧结论相比，当前远程部署的 0key 能力发生了明显变化：

- 默认论文源本轮表现最好：WARP 关闭时 5/6 可用，WARP 开启后 6/6 可用。
- 可手动选择的额外论文源中，WARP 开启后有 7/9 返回结果。
- Google Patents 当前不应计入实用可用源：多查询、多 backend、多 WARP 组合均未返回专利结果。
- 网页搜索显著弱于旧报告：本轮返回结果主要集中在 DuckDuckGo、Baidu、Yahoo、Bing CN，具体组合会随 backend、WARP 出口和上游反爬状态波动；不能把某个网页源作为固定承诺。
- `httpx` 不适合作为网页 scraper backend；即使开启 WARP，复测也没有形成可重复结果。

### 控制面状态

| 项目 | 远程实测结果 | 说明 |
|------|--------------|------|
| 认证状态 | 无 Bearer Token 返回 `role=admin` | 当前部署显式开放管理端，无需密码 |
| 搜索相关 Key | 论文/专利/网页搜索 Key 均为空 | Bilibili 凭据不属于本报告范围 |
| HTTP backend | `default_http_backend=auto`, `http_backend={}` | `PUT /api/v1/admin/http-backend` 可用 |
| HTTP backend GET | 当次观测为 500 `internal_error` | 这是控制面读取端点异常，已纳入 CD 回归修复；本报告当次矩阵通过 `PUT` 响应确认切换成功 |
| WARP 初始状态 | `disabled` | 测试结束后已恢复 |
| WARP 可用模式 | `wireproxy=true`; `kernel/usque/warp-cli=false`; `external` 未配置 | `POST /warp/enable?mode=auto` 实际启用 `wireproxy` |
| WARP 出口 | `104.28.196.75` | 本次启用 WARP 时观测到的出口 IP |

### 测试矩阵

| 维度 | 选项 | 说明 |
|------|------|------|
| WARP 代理 | 关 / 开 | Cloudflare WARP 隧道；当前 Docker 部署可用 `wireproxy` |
| HTTP 后端 | `curl_cffi` / `httpx` | 网页 scraper 和 Google Patents 受此设置影响 |

- 默认论文源（OpenAlex、CrossRef、arXiv、DBLP、PubMed、bioRxiv）主要走开放 API，按 WARP 开关测试。
- 网页搜索使用 `/api/v1/search/web`，按 `WARP × HTTP backend` 做 2×2 测试。
- 对网页搜索失败项又做了单引擎复核，避免把聚合请求失败误判为源不可用。
- `default_http_backend=auto` 在当前实现下仍建议保留；本报告的 2×2 矩阵用显式 `curl_cffi/httpx` 来验证边界，并用 `auto + WARP` 做推荐配置 spot check。

---

## 论文搜索

### 默认论文源

> 请求：`/api/v1/search/paper?q=machine+learning&sources=openalex,crossref,arxiv,dblp,pubmed,biorxiv&per_page=5`

| 数据源 | WARP 关 | WARP 开 | 说明 |
|--------|---------|---------|------|
| OpenAlex | 可用，5 条 | 可用，5 条 | 本轮可用 |
| CrossRef | 可用，5 条 | 可用，5 条 | 本轮可用 |
| arXiv | 可用，5 条 | 可用，5 条 | 本轮可用 |
| DBLP | 失败 | 可用，5 条 | 明显依赖 WARP |
| PubMed | 可用，5 条 | 可用，5 条 | 本轮可用 |
| bioRxiv | 可用，5 条 | 可用，5 条 | 本轮可用 |
| **可用源数** | **5/6** | **6/6** | WARP 主要补齐 DBLP |

### 额外零 Key 论文源

> 请求：WARP 开启后手动指定 `semantic_scholar,huggingface,europepmc,pmc,doaj,zenodo,hal,openaire,iacr`，每源 3 条。

| 数据源 | WARP 开 | 说明 |
|--------|---------|------|
| Semantic Scholar | 失败 | 免 Key 模式仍不稳定 |
| HuggingFace Papers | 失败 | 当前远程查询未返回结果 |
| Europe PMC | 可用，3 条 | 可作为额外论文源 |
| PMC | 可用，3 条 | 可作为额外论文源 |
| DOAJ | 可用，3 条 | 虽有可选 Key，当前匿名可返回结果 |
| Zenodo | 可用，3 条 | 虽有可选 Token，当前匿名可返回结果 |
| HAL | 可用，3 条 | 可作为额外论文源 |
| OpenAIRE | 可用，3 条 | 虽有可选 Key，当前匿名可返回结果 |
| IACR | 可用，3 条 | 实验性 HTML 爬虫，但本次可用 |
| **可用源数** | **7/9** | 适合手动扩展论文覆盖面 |

**结论**: 0key 论文搜索是当前远程部署本轮表现最好的部分。推荐保持默认 6 个论文源；需要更大覆盖面时，可额外启用 Europe PMC、PMC、DOAJ、Zenodo、HAL、OpenAIRE、IACR。

---

## 专利搜索

> 请求：`/api/v1/search/patent`，源为 `google_patents`。
> 复核查询：`machine learning`、`artificial intelligence`、`semiconductor`。

| HTTP 后端 | WARP 关 | WARP 开 | 说明 |
|-----------|---------|---------|------|
| `curl_cffi` | HTTP 200，但 0 条 | HTTP 200，失败/0 条 | 无实用结果 |
| `httpx` | HTTP 200，但 0 条 | HTTP 200，失败/0 条 | 无实用结果 |

Google Patents 在部分请求中会被端点计入 `succeeded`，但 `total=0` 且结果集为空；WARP 开启后还出现 `failed=["google_patents"]`。因此当前远程 0key 场景下，**不应把 Google Patents 计入可用专利源**。

需要可重复的专利检索时，仍应优先配置官方或代理型专利数据源，例如 EPO、USPTO、Lens、CNIPA、PatSnap，或修复 Google Patents 爬虫解析。

---

## 网页搜索

> 请求：`/api/v1/search/web?q=machine+learning&engines=...&max_results=5`。
> 当前 scraper 引擎覆盖 10 个：DuckDuckGo、Bing、Bing CN、Yahoo、Baidu、Mojeek、Yandex、Brave、Google、Startpage。

### 2×2 矩阵

| 引擎 | `curl_cffi` + WARP 关 | `curl_cffi` + WARP 开 | `httpx` + WARP 关 | `httpx` + WARP 开 |
|------|:---------------------:|:---------------------:|:-----------------:|:-----------------:|
| DuckDuckGo | 失败 | 可用，5 条 | 失败 | 失败 |
| Bing | 失败 | 失败 | 失败 | 失败 |
| Bing CN | 失败 | 波动，0~5 条 | 失败 | 波动，0~5 条 |
| Yahoo | 可用，5 条 | 波动，1~5 条 | 失败 | 失败 |
| Baidu | 可用，5 条 | 可用，5 条 | 失败 | 失败 |
| Mojeek | 失败 | 失败 | 失败 | 失败 |
| Yandex | 失败 | 失败 | 失败 | 失败 |
| Brave | 失败 | 失败 | 失败 | 失败 |
| Google | 失败 | 失败 | 失败 | 失败 |
| Startpage | 失败 | 失败 | 失败 | 失败 |
| **可重复/近似可用引擎数** | **2/10** | **约 3/10** | **0/10** | **0/10 可重复** |

### 单引擎复核

在 `curl_cffi + WARP 开` 下，逐个请求与聚合请求复核确认：

- 可重复性较好的返回：DuckDuckGo、Baidu。
- Yahoo 在不同复核中有返回，但结果条数波动。
- Bing CN 在部分聚合请求和 `auto + WARP` spot check 中可返回结果，但不稳定，不计入固定承诺。
- 仍未形成可重复结果：Bing、Mojeek、Yandex、Brave、Google、Startpage。

在 `httpx + WARP 开` 下，逐个复核 DuckDuckGo、Bing、Bing CN、Yahoo、Baidu 均未形成可重复结果；Bing CN 的偶发返回按波动结果处理，不计入可重复可用数。

### 推荐配置复核

在 `default_http_backend=auto + WARP 开` 的补充复核中，网页搜索同样返回 15 条结果，但引擎组合变为 DuckDuckGo、Baidu、Bing CN；Yahoo 在这次 spot check 中未返回结果。这说明推荐配置下网页 0key 能力大致维持在 **约 3/10**，但具体可用引擎会随上游反爬、出口 IP 和搜索引擎响应波动，不能把 Yahoo 或 Bing CN 作为固定承诺。

### 关键发现

1. `httpx` 不适合作为网页 scraper backend：WARP 关闭全失败，WARP 开启也未形成可重复结果。
2. `curl_cffi` 仍是网页搜索的必要条件；本轮它主要支撑 Baidu/Yahoo 这类低反爬源，其中 Yahoo 有波动；WARP 开启后又支撑 DuckDuckGo。
3. WARP 对 DBLP 和 DuckDuckGo 有实际提升，但没有恢复 Bing、Mojeek、Yandex；Bing CN 只适合按波动源记录。
4. Brave、Google、Startpage 在当前远程部署下仍不可用。
5. 旧报告中 “`curl_cffi + WARP` 可解锁 Mojeek/Yandex，Bing 稳定可用” 的结论已不适用于当前部署。

---

## 需要 Key 或自建实例的网页源

### API 引擎（需要 Key）

| 引擎 | 所需配置 | 说明 |
|------|----------|------|
| Tavily | `tavily_api_key` | AI 搜索 |
| Exa | `exa_api_key` | 语义搜索 |
| Serper | `serper_api_key` | Google SERP API |
| Brave API | `brave_api_key` | Brave 官方 API |
| SerpAPI | `serpapi_api_key` | 多引擎 SERP |
| Firecrawl | `firecrawl_api_key` | 搜索+爬取 |
| Perplexity | `perplexity_api_key` | Sonar AI 搜索 |
| Linkup | `linkup_api_key` | 实时搜索 |
| XCrawl | `xcrawl_api_key` | 搜索+抓取 |
| ScrapingDog | `scrapingdog_api_key` | SERP 代理 |
| Metaso | `metaso_api_key` | 秘塔搜索 |
| ZhipuAI | `zhipuai_api_key` | 智谱 Web Search |
| Aliyun IQS | `aliyun_iqs_api_key` | 通义晓搜 |

### 自建实例引擎

| 引擎 | 所需配置 | 说明 |
|------|----------|------|
| SearXNG | `searxng_url` | 元搜索引擎（需自建） |
| Whoogle | `whoogle_url` | Google 代理（需自建） |
| Websurfx | `websurfx_url` | 聚合搜索（需自建） |

---

## 总结：当前可用性

| 组合 | 默认论文 | 额外论文 | 专利 | 网页 | 评价 |
|------|:--------:|:--------:|:----:|:----:|------|
| `httpx` + WARP 关 | 5/6 | 未测 | 0/1 | 0/10 | 不推荐 |
| `httpx` + WARP 开 | 6/6 | 7/9 | 0/1 | 0/10 可重复 | 不推荐用于网页 |
| `curl_cffi` + WARP 关 | 5/6 | 未测 | 0/1 | 2/10 | 可临时使用 |
| **`curl_cffi/auto` + WARP 开** | **6/6** | **7/9** | **0/1** | **约 3/10** | **当前最佳 0key 组合** |

> 专利列按“能返回实际结果”计数，不把 HTTP 200 但 `total=0` 计为可用。

---

## 推荐配置

### 零成本最大化

保持默认 HTTP backend，并开启 WARP：

```bash
curl -X PUT "https://blueskyxn-souwen.hf.space/api/v1/admin/http-backend?default=auto"
curl -X POST "https://blueskyxn-souwen.hf.space/api/v1/admin/warp/enable?mode=auto&socks_port=1080&http_port=0"
```

该组合当前可获得：

- 默认论文源 6 个：OpenAlex、CrossRef、arXiv、DBLP、PubMed、bioRxiv。
- 额外论文源 7 个：Europe PMC、PMC、DOAJ、Zenodo、HAL、OpenAIRE、IACR。
- 网页搜索约 3 个：显式 `curl_cffi + WARP` 与 `auto + WARP` 的返回组合在 DuckDuckGo、Baidu、Yahoo、Bing CN 之间波动，不能固定承诺某三个源。

### 不建议依赖

- 不建议把 Google Patents 作为当前 0key 专利能力对外承诺。
- 不建议在网页搜索场景切到 `httpx`。
- 不建议继续宣传 Bing、Bing CN、Mojeek、Yandex 在当前 HF Space 上固定可用，除非后续单独修复并复测。

---

## 失败源分析

| 源 | 当前表现 | 可能原因 | 建议 |
|----|----------|----------|------|
| Google Patents | 多查询均 0 条或失败 | Google Patents 页面/XHR 结构或反爬策略变化 | 修复爬虫解析，或接入官方专利 API |
| Bing / Bing CN | 当前波动或失败 | 页面结构/反爬变化；聚合与单引擎复核不一致 | 不计入可重复可用源，后续单独排查 |
| Mojeek / Yandex | WARP 开启后仍失败 | 出口 IP 或解析策略不再适配 | 后续针对页面结构和返回状态排查 |
| Brave / Google / Startpage | 持续失败 | 高强度反爬、验证码或 JS Challenge | 使用 Brave API、Serper、SerpAPI 等替代 |
| Semantic Scholar | 免 Key 失败 | 匿名限流严格 | 配置 `semantic_scholar_api_key` |
| HuggingFace Papers | 当前未返回结果 | 远程查询链路或解析不稳定 | 单独排查客户端实现 |

---

## 与旧报告对比

| 项目 | 2026-04-18 旧结论 | 2026-05-02 当前结论 |
|------|------------------|---------------------|
| SouWen 版本 | v0.6.3 | v1.1.1 |
| 默认论文源 | 5/6 左右，S2 波动 | WARP 关 5/6，WARP 开 6/6 |
| 额外论文源 | 未覆盖 | WARP 开 7/9 可用 |
| 专利源 | Google Patents WARP 后稳定 | Google Patents 无实际结果，不计入可用 |
| 网页引擎范围 | 9 个 scraper 引擎 | 10 个 scraper 引擎，新增 Bing CN |
| 最佳网页组合 | `curl_cffi + WARP` 可用 6/9 | `curl_cffi/auto + WARP` 约 3/10，具体引擎会波动 |
| Mojeek / Yandex | WARP 后可用 | 当前不可用 |
| Bing | 多组合可用 | 当前不可用或波动 |
| 推荐组合 | `auto + WARP` 可获 12/16 | `auto + WARP` 仍最佳，但能力边界应降级描述 |
