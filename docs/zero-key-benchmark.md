# 无 API Key 场景实测报告

> **测试环境**: Hugging Face Spaces (免费 CPU 实例)
> **SouWen 版本**: v0.6.3
> **测试时间**: 2026-04-18
> **部署地址**: https://blueskyxn-souwen.hf.space

## 概述

SouWen 的设计理念是**零配置可用** — 尽可能多的数据源无需 API Key 即可工作。本文档记录了在无任何 API Key 的 HF Spaces 环境下，各数据源在 **2×2 组合矩阵**（WARP 开关 × HTTP 后端）下的真实表现。

### 测试矩阵

| 维度 | 选项 | 说明 |
|------|------|------|
| WARP 代理 | 关 / 开 | Cloudflare WARP 隧道，提供干净出口 IP |
| HTTP 后端 | curl_cffi / httpx | curl_cffi 支持 TLS 指纹模拟（Chrome），httpx 为标准 Python HTTP 库 |

- **论文/专利源**始终使用 `httpx`（通过 SouWenHttpClient），不受 HTTP 后端设置影响，仅有 WARP 开关维度。
- **网页搜索引擎**使用 `BaseScraper`，完整 2×2 矩阵适用。
- 默认配置 `default_http_backend: auto` 在 curl_cffi 可用时自动选择 curl_cffi。

---

## 论文搜索

> 始终使用 httpx，HTTP 后端设置无影响。测试查询：`machine learning`

| 数据源 | WARP 关 | WARP 开 | 说明 |
|--------|---------|---------|------|
| OpenAlex | ✅ | ✅ | 最稳定，覆盖 2.5 亿篇文献 |
| CrossRef | ✅ | ✅ | DOI 元数据，覆盖面广 |
| PubMed | ✅ | ✅ | 生物医学文献 |
| arXiv | ⚠️ 间歇 | ✅ | 预印本；WARP 关闭时偶尔不可用 |
| DBLP | ❌ | ✅ | 计算机科学；需要 WARP |
| Semantic Scholar | ⚠️ 间歇 | ⚠️ 间歇 | 免 Key 限流严格；可用性波动 |
| CORE | — | — | 需要 API Key，未测试 |

**结论**: WARP 关闭时 **3~5/6** 稳定可用，开启后 **5/6** 可用（S2 波动）。

---

## 专利搜索

> 始终使用 httpx，HTTP 后端设置无影响。

| 数据源 | WARP 关 | WARP 开 | 说明 |
|--------|---------|---------|------|
| Google Patents | ⚠️ 间歇 | ✅ | 爬虫模式；WARP 显著提升稳定性 |

需要 API Key 的专利源（EPO、USPTO、Lens、CNIPA、PatSnap）不在零配置测试范围内。

---

## 网页搜索 — 2×2 完整矩阵

> 使用 BaseScraper，受 HTTP 后端设置影响。测试查询：`machine learning`

### 爬虫引擎（无需 Key）

| 引擎 | curl_cffi WARP关 | curl_cffi WARP开 | httpx WARP关 | httpx WARP开 |
|------|:-:|:-:|:-:|:-:|
| DuckDuckGo | ✅ 10 | ✅ 10 | ❌ 0 | ✅ 10 |
| Bing | ✅ 10 | ✅ 10 | ❌ 0 | ✅ 10 |
| Yahoo | ✅ 7 | ✅ 7 | ❌ 0 | ✅ 7 |
| Baidu | ✅ 7 | ✅ 7 | ❌ 0 | ✅ 7 |
| Mojeek | ❌ 0 | ✅ 10 | ❌ 0 | ❌ 0 |
| Yandex | ❌ 0 | ✅ 10 | ❌ 0 | ❌ 0 |
| Brave | ❌ 0 | ❌ 0 | ❌ 0 | ❌ 0 |
| Google | ❌ 0 | ❌ 0 | ❌ 0 | ❌ 0 |
| Startpage | ❌ 0 | ❌ 0 | ❌ 0 | ❌ 0 |
| **可用引擎数** | **4/9** | **6/9** | **0/9** | **4/9** |

### 关键发现

1. **httpx 裸跑 = 全军覆没**: 无 TLS 指纹模拟 + 无 WARP → 所有引擎反爬拦截
2. **curl_cffi 是核心**: TLS 指纹模拟使 DDG/Bing/Yahoo/Baidu 无需 WARP 即可使用
3. **WARP 补位 httpx**: WARP 出口 IP 可让 DDG/Bing/Yahoo/Baidu 在 httpx 下恢复
4. **curl_cffi + WARP 最强**: 唯一能解锁 Mojeek + Yandex 的组合（需双重条件）
5. **三者永远无法爬取**: Brave/Google/Startpage 无论何种组合均失败

### API 引擎（需要 Key，未测试）

| 引擎 | 所需 Key | 说明 |
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

### 自建实例引擎（需要 URL，未测试）

| 引擎 | 所需配置 | 说明 |
|------|----------|------|
| SearXNG | `searxng_url` | 元搜索引擎（需自建） |
| Whoogle | `whoogle_url` | Google 代理（需自建） |
| Websurfx | `websurfx_url` | 聚合搜索（需自建） |

---

## 总结：各组合可用源数

| 组合 | 论文 | 专利 | 网页 | 总计 | 评价 |
|------|:----:|:----:|:----:|:----:|------|
| httpx + WARP 关 | 3~5/6 | 0~1/1 | 0/9 | **3~6/16** | ⛔ 不可用 |
| httpx + WARP 开 | 5/6 | 1/1 | 4/9 | **10/16** | ⚠️ 勉强可用 |
| curl_cffi + WARP 关 | 3~5/6 | 0~1/1 | 4/9 | **7~10/16** | ✅ 基本可用 |
| **curl_cffi + WARP 开** | **5/6** | **1/1** | **6/9** | **12/16** | ✅✅ **推荐配置** |

> 论文/专利列的范围表示间歇性源（arXiv、Google Patents）的波动。

---

## WARP 代理效果

WARP 对被 IP 限制的源效果显著（arXiv、DBLP、Google Patents、Mojeek、Yandex），对使用高级反爬技术的源（Google、Startpage、Brave）无效。

### 启用 WARP

```bash
# API 方式
curl -X POST http://localhost:8000/api/v1/admin/warp/enable

# 或在 Panel 面板中点击 WARP 开关
```

---

## 推荐配置（零成本最大化）

**保持 `default_http_backend: auto`（默认）+ 开启 WARP** 即可获得：

- **5 个论文源**: OpenAlex, CrossRef, PubMed, arXiv, DBLP
- **1 个专利源**: Google Patents
- **6 个网页引擎**: DuckDuckGo, Bing, Yahoo, Baidu, Mojeek, Yandex

共 **12 个数据源**，覆盖学术论文、专利、网页三大领域。

---

## 失败源分析

| 源 | 失败原因 | 可能的解决方案 |
|----|----------|----------------|
| Google (web) | 反爬检测（验证码+JS Challenge） | 使用 SerpAPI/Serper API 替代 |
| Startpage | Google 后端同样被封 | 使用 SerpAPI/Serper API 替代 |
| Brave (web) | 反爬检测，超时 | 使用 Brave API（`brave_api_key`）替代 |
| Semantic Scholar | 免 Key 限流严格 | 申请免费 API Key |

---

## 与 v0.3.0 对比

| 变化项 | v0.3.0 | v0.6.3 |
|--------|--------|--------|
| 专利源架构 | PatentsView + PQAI + Google Patents | EPO/USPTO/Lens/CNIPA/PatSnap + Google Patents |
| 零配置专利源 | 3 个（均失败） | 1 个（Google Patents，WARP 后稳定） |
| HTTP 后端 | curl_cffi | auto（优先 curl_cffi，回退 httpx） |
| 最佳组合零配置总可用 | ~8 | **12/16**（curl_cffi + WARP） |
| 安全加固 | 无 | SSRF 防护、DNS 校验、重定向验证 |
