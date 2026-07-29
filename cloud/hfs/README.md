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

## 在线预览

Space 仓库保持 `private=true`。当前 App domain 允许匿名读取 Panel shell、Swagger、OpenAPI
和 probes；Data/Admin API 仍要求 SouWen application credential，且 production 不开启
`SOUWEN_ADMIN_OPEN`。根 App 当前跳转到 Swagger，产品界面请使用 Panel 直达链接。

| Workspace | 直达链接 | 最低角色 |
|---|---|---|
| Login | <https://blueskyxn-souwen.hf.space/panel#/login> | 无 |
| Search | <https://blueskyxn-souwen.hf.space/panel#/search> | user |
| LLM Search | <https://blueskyxn-souwen.hf.space/panel#/llm-search> | user |
| Fetch | <https://blueskyxn-souwen.hf.space/panel#/fetch> | user |
| Providers | <https://blueskyxn-souwen.hf.space/panel#/providers> | user |
| Runtime | <https://blueskyxn-souwen.hf.space/panel#/runtime> | admin |
| Settings | <https://blueskyxn-souwen.hf.space/panel#/settings> | admin |
| Swagger | <https://blueskyxn-souwen.hf.space/docs> | 无 |

Panel 登录框接收 SouWen application token，不接收 HF write token。不要把 token 放进 URL、
Issue、截图或日志。完整逐项验收见
[HFS 在线预览指南](https://github.com/BlueSkyXN/SouWen/blob/main/docs/live-preview.md)。

## RC4 进程拓扑

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
| GET | `/api/v1/whoami` | 当前 application role 与安全 feature projection |
| POST | `/api/v1/search` | RC4 canonical Search |
| POST | `/api/v1/llm-search` | RC4 canonical LLM Search；正式 promotion 必须配置并 live 验证 |
| POST | `/api/v1/fetch` | RC4 canonical Fetch + private Browser Worker fallback |
| GET | `/api/v1/providers` | RC4 Provider availability catalog |
| GET | `/api/v1/admin/config` | 查看配置（需认证） |
| GET | `/api/v1/admin/doctor` | 数据源健康检查（需认证） |
| GET | `/api/v1/admin/ping` | Admin 认证存活检查（需认证） |

## 当前 HFS settings ownership

Candidate-pinned GitHub Actions 是唯一 settings writer。Space 当前只登记名称，不在仓库、
Space card、日志或 evidence 中保存真实值：

| 类型 | 名称 | 所有权 / 用途 |
|---|---|---|
| Secret | `SOUWEN_ADMIN_PASSWORD` | read-only Admin application auth |
| Secret | `SOUWEN_CONFIG_B64` | 完整 runtime YAML；包含 Data API 访问策略与 Provider 配置 |
| Secret | `UNIAPI_API_KEY` | 已配置 LLM Search Provider 的环境引用 |
| Variable | `SOUWEN_WRAPPER_SHA` | 当前 Space wrapper provenance；写入后立即 readback |

`SOUWEN_USER_PASSWORD` 不是当前独立 Space Secret 名称；Data API credential 由
`SOUWEN_CONFIG_B64` 对应的 runtime config 管理。`HF_TOKEN`、`HF_SPACE_READ_TOKEN` 和
`SOUWEN_SMOKE_BEARER_TOKEN` 属于 GitHub `hf` environment，不是 Space settings。

SouWen 采用当前 HFS v2.1 draft 的 `preview` / `primary` / `source` 分类（正式公开基线仍为
v2.0）：没有 SouWen Bucket、`hfs-dist` object、Volume、seed 或 mounted config。
`hfs-dev.toml` 声明根 `.env` 为 mode `0600` 的 env 事实源，并登记同为 gitignored、`0600` 的
`local/credentials/souwen-hfs.yaml` 作为 `SOUWEN_CONFIG_B64` 的原始 YAML 事实源；Base64 不是
唯一事实源。Registry 保持 registry-only；通用 `hf_space_sync.py` 不得 push、pull、prune 或改写
这些 workflow-owned settings。

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

详细边界见
[HFS CD 与验收](https://github.com/BlueSkyXN/SouWen/blob/main/docs/hf-space-cd.md)。正式
promotion 的三项 capability live smoke 和 authenticated admin config/ping/doctor 都是 required。
Secret 值在 Space 端 write-only，因此 settings sync 开始后的任一失败都会 fail closed pause，
等待人工从获批 Secret source 恢复；不会运行“旧 wrapper + 新/部分 settings”。

`v2.0.0rc4` tag/GitHub prerelease 是 immutable Release baseline。HFS 可以部署 tag 之后的 exact
current main，并继续报告 package version `2.0.0rc4`；应通过 health/readiness source SHA、Space
repo/runtime/wrapper SHA 和 exact-source deployment evidence 判断当前部署，不能只看版本号。

## 源码

- 项目仓库：<https://github.com/BlueSkyXN/SouWen>
