---
title: SouWen 搜文
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 49265
pinned: false
---

# SouWen 搜文 — 学术搜索 API

面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API 服务。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 存活探针 |
| GET | `/readiness` | 就绪探针（v0.6.1，检查配置可加载 + 数据源注册表非空） |
| GET | `/api/v1/search/paper?q=...` | 搜索学术论文 |
| GET | `/api/v1/search/patent?q=...` | 搜索专利 |
| GET | `/api/v1/search/web?q=...` | 搜索网页（默认 `engines=duckduckgo,bing`） |
| GET | `/api/v1/sources` | 列出所有可用数据源 |
| GET | `/api/v1/admin/config` | 查看配置（需认证） |
| POST | `/api/v1/admin/config/reload` | 重载配置（需认证） |
| GET | `/api/v1/admin/doctor` | 数据源健康检查（需认证） |
| GET | `/api/v1/admin/warp` | 查询 WARP 状态（需认证） |
| POST | `/api/v1/admin/warp/enable` | 启用 WARP 代理（需认证） |
| POST | `/api/v1/admin/warp/disable` | 关闭 WARP 代理（需认证） |

## 配置

通过 HuggingFace Spaces 的 **Secrets** 注入环境变量：

| 变量 | 说明 |
|------|------|
| `SOUWEN_CONFIG_B64` | Base64 编码的 souwen.yaml 完整配置 |
| `SOUWEN_API_PASSWORD` | 旧版统一密码（向后兼容，同时作用搜索 + 管理） |
| `SOUWEN_VISITOR_PASSWORD` | v0.6.3：访客密码，仅保护搜索端点（优先级高于 `api_password`） |
| `SOUWEN_ADMIN_PASSWORD` | v0.6.3：管理密码，仅保护 `/api/v1/admin/*`（优先级高于 `api_password`） |
| `SOUWEN_ADMIN_OPEN` | 设为 `1` 时显式放行未配置密码的 admin 端点（仅本地/CI 调试用） |
| `SOUWEN_TRUSTED_PROXIES` | 受信反向代理 IP/CIDR 列表，逗号分隔（如 `10.0.0.0/8,127.0.0.1`） |
| `SOUWEN_EXPOSE_DOCS` | 是否暴露 `/docs`、`/redoc`、`/openapi.json`，生产建议 `false` |
| `SOUWEN_MAX_CONCURRENCY` | 聚合搜索并发上限，默认 `10`（v0.6.0） |
| `SOUWEN_OPENALEX_EMAIL` | OpenAlex 邮箱（免费，提升速率） |
| `SOUWEN_SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API Key |
| `SOUWEN_CORE_API_KEY` | CORE API Key |
| `SOUWEN_TAVILY_API_KEY` | Tavily AI 搜索 Key |
| `SOUWEN_SERPER_API_KEY` | Serper (Google SERP) Key |
| `SOUWEN_BRAVE_API_KEY` | Brave Search API Key |
| `WARP_ENABLED` | 设为 `1` 启用内嵌 Cloudflare WARP 代理（突破 IP 限制，常用于 DBLP / Semantic Scholar） |
| ... | 其他 SOUWEN_* 环境变量均可直接设置 |

> 大部分爬虫引擎（DuckDuckGo、Yahoo、Brave Scraper、Google Scraper 等）无需 API Key 即可使用。

## 源码

- 项目仓库：<https://github.com/BlueSkyXN/SouWen>
