# 无 API Key 场景实测报告

> **测试环境**: Hugging Face Spaces (免费 CPU 实例)
> **SouWen 版本**: v0.6.3
> **测试时间**: 2026-04-17
> **HTTP 后端**: httpx (默认)
> **部署地址**: https://blueskyxn-souwen.hf.space

## 概述

SouWen 的设计理念是**零配置可用** — 尽可能多的数据源无需 API Key 即可工作。本文档记录了在无任何 API Key 的 HF Spaces 环境下，各数据源的真实表现。

---

## 论文搜索

所有免费论文源均为公开 API，无需 Key。测试查询：`machine learning`

| 数据源 | WARP 关 | WARP 开 | 响应时间 | 说明 |
|--------|---------|---------|----------|------|
| OpenAlex | ✅ 10 条 | ✅ 正常 | ~2.6s | 最稳定的学术源，覆盖 2.5 亿篇文献 |
| Semantic Scholar | ✅ 10 条 | ⚠️ 不稳定 | ~2.5s | 免 Key 易限流；WARP IP 可能被限 |
| CrossRef | ✅ 10 条 | ✅ 正常 | ~2.4s | DOI 元数据，覆盖面广 |
| arXiv | ⚠️ 无结果 | ✅ 正常 | ~2.3s | 预印本，WARP 后恢复 |
| DBLP | ⚠️ 无结果 | ✅ 正常 | ~4.2s | 计算机科学，WARP 后恢复 |
| PubMed | ✅ 10 条 | ✅ 正常 | ~2.5s | 生物医学文献 |
| CORE | — | — | — | 需要 API Key，未测试 |

**结论**: WARP 关闭时 **4/6** 可用，开启后 **5/6** 可用（Semantic Scholar 波动）。

---

## 专利搜索

v0.6.3 专利源架构已重构（epo_ops / uspto_odp / the_lens / cnipa / patsnap 均需 Key），仅 Google Patents 为零配置爬虫。

| 数据源 | WARP 关 | WARP 开 | 响应时间 | 说明 |
|--------|---------|---------|----------|------|
| Google Patents | ⚠️ 无结果 | ✅ 1 条 | ~8.3s | 爬虫模式，WARP 后可用 |

**结论**: WARP 开启后 **1/1** 零配置专利源可用。

---

## 网页搜索

网页搜索引擎分为**爬虫引擎**（HTML 解析）和 **API 引擎**（需要 Key）。

### 爬虫引擎（无需 Key）

测试查询：`machine learning`

| 引擎 | WARP 关 | WARP 开 | 响应时间 | 说明 |
|------|---------|---------|----------|------|
| DuckDuckGo | ✅ 10 条 | ✅ 10 条 | ~4.8s | 最稳定，推荐默认引擎 |
| Bing | ✅ 10 条 | ✅ 10 条 | ~4.7s | 稳定可靠，速度快 |
| Yahoo | ✅ 7 条 | ✅ 7 条 | ~5.1s | 稳定可用 |
| Baidu | ✅ 7 条 | ✅ 7 条 | ~5.8s | 中文搜索表现好 |
| Mojeek | ❌ 无结果 | ✅ 10 条 | ~5.3s | 独立引擎，WARP 后恢复 |
| Brave | ❌ 无结果 | ❌ 无结果 | ~17s | 反爬较强，超时 |
| Google | ❌ 无结果 | ❌ 无结果 | ~7.5s | 反爬极强（验证码+JS Challenge） |
| Startpage | ❌ 无结果 | ❌ 无结果 | ~4.3s | 使用 Google 后端，同样被封 |
| Yandex | ❌ 无结果 | ❌ 无结果 | ~6.2s | 地域限制 + 反爬 |

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
| ScrapingDog | `scrapingdog_api_key` | SERP 代理 |

### 自建实例引擎（需要 URL，未测试）

| 引擎 | 所需配置 | 说明 |
|------|----------|------|
| SearXNG | `searxng_url` | 元搜索引擎（需自建） |
| Whoogle | `whoogle_url` | Google 代理（需自建） |
| Websurfx | `websurfx_url` | 聚合搜索（需自建） |

**结论**: WARP 关闭时 **4/9** 爬虫引擎可用，开启后 **5/9** 稳定可用。

---

## WARP 代理效果

| 指标 | WARP 关 | WARP 开 | 变化 |
|------|---------|---------|------|
| 论文源可用数 | 4/6 | 5/6 | +1（arXiv、DBLP 恢复；S2 波动） |
| 专利源可用数 | 0/1 | **1/1** | +1 |
| 网页引擎可用数 | 4/9 | **5/9** | +1（Mojeek 恢复） |
| **零配置总可用** | **8/16** | **11/16** | **+3** |

WARP 对被 IP 限制的源（arXiv、DBLP、Google Patents、Mojeek）效果显著。对使用高级反爬技术的源（Google、Startpage、Brave、Yandex）无效。

### 启用 WARP

```bash
# API 方式
curl -X POST http://localhost:8000/api/v1/admin/warp/enable

# 或在 Panel 面板中点击 WARP 开关
```

---

## 推荐配置（零成本）

无需任何 Key，开启 WARP 即可获得：
- **5 个论文源**: OpenAlex, CrossRef, arXiv, DBLP, PubMed
- **1 个专利源**: Google Patents（实验性）
- **5 个网页引擎**: DuckDuckGo, Bing, Yahoo, Baidu, Mojeek

共 **11 个数据源**，覆盖学术论文、专利、网页三大领域。

---

## 失败源分析

| 源 | 失败原因 | 可能的解决方案 |
|----|----------|----------------|
| Google (web) | 反爬检测（验证码+JS Challenge） | 暂不支持 |
| Startpage | Google 后端同样被封 | 暂不支持 |
| Brave (web) | 反爬检测，超时 ~17s | 暂不支持 |
| Yandex | 地域限制 + 反爬 | 使用俄罗斯 IP 代理 |
| Semantic Scholar | 免 Key 限流（WARP IP 可能被列入限流名单） | 申请免费 API Key |

---

## 与 v0.3.0 对比

| 变化项 | v0.3.0 | v0.6.3 |
|--------|--------|--------|
| 专利源架构 | PatentsView + PQAI + Google Patents | EPO/USPTO/Lens/CNIPA/PatSnap + Google Patents |
| 零配置专利源 | 3 个（均失败） | 1 个（Google Patents，WARP 后可用） |
| HTTP 后端 | curl_cffi | httpx（默认） |
| WARP 后论文源 | 6/6 | 5/6（S2 波动） |
| WARP 后网页引擎 | 5/13 | 5/9（旧源如 Qwant/Sogou/Ecosia/Wikipedia 已移除） |
| 安全加固 | 无 | SSRF 防护、DNS 校验、重定向验证 |
