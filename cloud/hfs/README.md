---
title: SouWen 搜文
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 49265
pinned: false
---

# SouWen 搜文 — Information Retrieval API

面向 AI Agent 的 target-only Search、LLM Search 与 Fetch API 服务。

## RC2 进程拓扑

HFS wrapper 只向外暴露 `49265`。`deploy/process/supervisor.py` 先在
`127.0.0.1:49266` 启动 authenticated Browser Worker，并验证 contract/source/version/config/
inventory readiness；成功后才启动 API。Worker token 每次启动生成，不写入配置、日志或探针。
Worker 异常时 API health 可继续响应，但 `/readyz` 必须 fail closed；重启次数有上限。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz`、`/health` | 同 handler 存活探针；回读 version/source/wrapper/rollout |
| GET | `/readyz`、`/readiness` | 同 handler 就绪探针；聚合 API、Provider 与 Browser Worker |
| GET | `/docs` | OpenAPI / Swagger UI 文档 |
| GET | `/panel` | 管理面板 HTML；浏览器访问入口为 `/panel#/` |
| GET | `/openapi.json` | OpenAPI schema |
| POST | `/api/v1/search` | RC2 canonical Search |
| POST | `/api/v1/llm-search` | RC2 canonical LLM Search；正式 promotion 必须配置并 live 验证 |
| POST | `/api/v1/fetch` | RC2 canonical Fetch + private Browser Worker fallback |
| GET | `/api/v1/providers` | RC2 Provider availability catalog |
| GET | `/api/v1/admin/config` | 查看配置（需认证） |
| GET | `/api/v1/admin/doctor` | 数据源健康检查（需认证） |

## 配置

通过 HuggingFace Spaces 的 **Secrets** 注入环境变量：

| 变量 | 说明 |
|------|------|
| `SOUWEN_CONFIG_B64` | Base64 编码的 souwen.yaml 完整配置；同时配置为 GitHub `hf` environment secret 供 promotion fail-fast 校验 |
| `SOUWEN_USER_PASSWORD` | 用户密码，保护 target Data API（Search/LLM Search/Fetch/Providers） |
| `SOUWEN_ADMIN_PASSWORD` | 管理密码，保护 read-only admin endpoints |
| `SOUWEN_GUEST_ENABLED` | 设为 `true` 时允许无 Token 访问搜索端点 |
| `SOUWEN_ADMIN_OPEN` | 不要在 Space 中配置；private Space 仍必须使用 `SOUWEN_ADMIN_PASSWORD` 保护管理端点 |
| `SOUWEN_TRUSTED_PROXIES` | 受信反向代理 IP/CIDR 列表，逗号分隔（如 `10.0.0.0/8,127.0.0.1`） |
| `SOUWEN_EXPOSE_DOCS` | 是否暴露 `/docs`、`/redoc`、`/openapi.json`，生产建议 `false` |
| `SOUWEN_MAX_CONCURRENCY` | 聚合搜索并发上限，默认 `10`（v0.6.0） |
| `SOUWEN_OPENALEX_API_KEY` | OpenAlex Freemium API Key（可选；额度/预付余额以账户为准） |
| `SOUWEN_OPENALEX_EMAIL` | 已弃用兼容字段（当前不发送给 OpenAlex） |
| `SOUWEN_SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API Key |
| `SOUWEN_CORE_API_KEY` | CORE API Key |
| `SOUWEN_TAVILY_API_KEY` | Tavily AI 搜索 Key |
| `SOUWEN_SERPER_API_KEY` | Serper (Google SERP) Key |
| `SOUWEN_BRAVE_API_KEY` | Brave Search API Key |
| `WARP_ENABLED` | 设为 `1` 启用内嵌 Cloudflare WARP 代理（突破 IP 限制，常用于 DBLP / Semantic Scholar） |
| ... | 其他 SOUWEN_* 环境变量均可直接设置 |

> 大部分爬虫引擎（DuckDuckGo、Yahoo、Brave Scraper、Google Scraper 等）无需 API Key 即可使用。

## 部署与验收

GitHub 上的 `HF Space CD` workflow 在 PR 和直接手动触发时只运行本地预检：SDK/Server
contract、HF Space Docker 容器启动和 API surface smoke。合入或 push `main` 不会
自动部署。只有当前 `main` 上的 central `release-candidate.yml` 在人工批准并显式设置
`deploy_hfs=true` 后，才会同步本目录 wrapper、触发 Space factory rebuild，并在远端分
`surface` / `capability` 两个 smoke job 执行部署后验收。

`Dockerfile` 是 fail-closed 模板：仓库中的全零 `SOUWEN_REF` 不能直接构建。
部署 workflow 会在临时 staging 目录把它替换为经验证的 40 位 candidate SHA，
同步后再回读远端 Dockerfile。容器内 `/health` 与 `/readiness` 的
`source_sha` 必须与该 SHA 完全一致；workflow 同时把实际 Space wrapper commit 写入
`SOUWEN_WRAPPER_SHA` variable，探针 `wrapper_sha` 必须与 repo/runtime SHA 一致。Capability
报告还必须证明 `rollout_mode=target`、非空 `config_revision`、`browser_worker=ready`，并真实执行
Search、LLM Search 与 immutable Fetch；禁止回退到 floating `main`。

部署后人工验收至少访问：

- 管理面板：<https://blueskyxn-souwen.hf.space/panel#/>
- API 文档：<https://blueskyxn-souwen.hf.space/docs>

详细边界见 `docs/hf-space-cd.md`。正式 promotion 的三项 capability live smoke 都是 required；
任一失败会触发 rollback/pause 流程，不能作为成功发布证据。

## 源码

- 项目仓库：<https://github.com/BlueSkyXN/SouWen>
