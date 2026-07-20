# Hugging Face Space CD 与验收

本文说明 SouWen 的 Hugging Face Space 本地预检、受控 promotion、双层认证、provenance
与失败恢复边界。RC promotion 还必须满足
[v2.0.0rc1 发布候选门禁](./internal/rc-readiness-gates.md)。未经明确批准，不得同步 Space
仓库、factory rebuild、修改 secrets 或触发远端 smoke。

## 部署对象与访问边界

- 应用入口：<https://blueskyxn-souwen.hf.space/>
- 管理面板：<https://blueskyxn-souwen.hf.space/panel#/>
- OpenAPI 文档：<https://blueskyxn-souwen.hf.space/docs>
- Space 仓库：<https://huggingface.co/spaces/BlueSkyXN/SouWen>

目标 Space 必须在 promotion 前已是 `private=true`。仓库可见性与应用鉴权是两个独立结论：
private Space 的 edge 访问仍需 Hugging Face READ token；进入应用后，SouWen admin API 还必须
由独立的 admin password 保护。不能用“Space 是 private”推导“匿名请求不可能获得 admin”。

`/panel#/` 中的 `#` 是前端 hash router 片段，不会发送到服务端；服务端实际校验 `/panel`。
这些固定 URL 在 private Space 下不代表匿名公开可访问，调用方必须遵守 Hugging Face 的访问策略。

## GitHub Actions 分层

`.github/workflows/deploy-hf-space.yml` 同时承担 local preflight 与 reusable promotion：

- `pull_request`：只运行本地 API/CLI、PyInstaller 和 HFS Docker smoke。
- 直接 `workflow_dispatch`：只运行本地 preflight，不写远端。
- 合入或 push `main`：**不会自动部署**。
- 远端 promotion：只能由 `.github/workflows/release-candidate.yml` 从当前 `main` control plane
  调用，并显式设置 `deploy_hfs=true`。

Central workflow 的默认输入是 `publish=false`、`deploy_hfs=false`。默认运行只生成 RC-ready
证据和 release bundle，不创建 tag/Release，也不写 HFS。`deploy_hfs=true` 时，candidate 必须
等于当前 `origin/main`；不能从未合入分支向持有 secrets 的部署 job 注入 verifier。

### Local preflight

| Job | 覆盖内容 | 边界 |
|---|---|---|
| `Resolve deploy eligibility` | 解析入口与 candidate contract | direct dispatch 不具备远端写资格 |
| `API surface and source CLI` | `pro-cli`、`basic-cli` profile | 不证明外部源在线 |
| `PyInstaller CLI smoke` | `edition-basic` 单文件 binary，保留 MCP | 不等于 24-binary release matrix |
| `HF Space Docker surface smoke` | exact SHA 构建、启动、health/readiness/docs/panel | 本地容器，不是 live Space |

HFS Docker build 必须传 `SOUWEN_REF=<40位 candidate SHA>`。Dockerfile 的全零模板、短 SHA、
分支名和 moving `main` 都 fail closed；detached checkout 会把 SHA 写入
`/app/runtime.source.sha`，由 `/health.source_sha` 与 `/readiness.source_sha` 回读。

## Private Space 双层认证

Hugging Face 官方 private Space HTTP 入口占用标准 `Authorization: Bearer <HF token>`。
因此 promotion smoke 使用两个不同 secrets，禁止复用高权限凭据：

| Secret | 用途 | 请求通道 |
|---|---|---|
| `HF_TOKEN` | 写 Space repo、restart/pause runtime | 仅 HFS 管理 API；需要 write 权限 |
| `HF_SPACE_READ_TOKEN` | 通过 private Space edge | `Authorization: Bearer ...`；只需 READ |
| `SOUWEN_SMOKE_BEARER_TOKEN` | SouWen 应用 admin password | `X-SouWen-Token: ...` |

SouWen 仍以标准 `Authorization: Bearer <password>` 作为普通部署的首选应用鉴权。只有上游
代理已经占用 `Authorization` 时才使用 `X-SouWen-Token`；显式 custom header 优先，若其值
无效，不会回退到另一个 header。远端必须删除/关闭 `SOUWEN_ADMIN_OPEN`，配置真实
`SOUWEN_ADMIN_PASSWORD`，并让 `SOUWEN_SMOKE_BEARER_TOKEN` 与其一致。

Post-deploy harness 从 central workflow 的受信 `verifier_sha` checkout 运行，不执行 candidate
checkout 中的 secret-bearing 脚本。验收同时证明：

1. `HF_SPACE_READ_TOKEN` 能通过 private edge。
2. 携带独立 SouWen token 时 `/api/v1/whoami` 为 `role=admin && admin_open=false`。
3. 只通过 HF edge、不提供 SouWen token 时，不得获得 admin。

## Provenance 三段模型

三个 SHA 不能混为一谈：

| 字段 | 含义 | 必须满足 |
|---|---|---|
| `candidate_sha` / `source_sha` | SouWen 源码 commit | health/readiness `source_sha == candidate_sha` |
| `space_repo_sha` | Space wrapper 仓库 commit | 该 revision 的 Dockerfile 精确 pin `SOUWEN_REF=<candidate_sha>` |
| `runtime.raw.sha` | HF 当前运行的 wrapper revision | `runtime.raw.sha == space_repo_sha` |

`RUNNING`、版本相同或 Space repo SHA 单独都不能证明 candidate 已接管。Manifest 应分别保存
`hfs.repo_sha`、`hfs.runtime_sha` 与 `hfs.source_sha`，不能要求 wrapper SHA 等于 SouWen source
SHA。

## Promotion 与恢复事务

远端 promotion 依次执行：

1. 在任何 wrapper mutation 前唤醒旧 runtime（若处于 sleeping），要求旧 Space repo SHA 与
   runtime SHA 相等，并从旧 Dockerfile 解析唯一的 40 位 `SOUWEN_REF`。
2. 记录 `prior_space_commit_sha`、`prior_runtime_commit_sha`、`prior_souwen_ref`。旧部署没有
   immutable source pin 时，在写入前停止，不能回退到 floating `main`。
3. 只同步受管的四个 wrapper 文件；diff 固定读取 prior revision，`create_commit` 使用
   `parent_commit=<prior_space_commit_sha>` 防止外部 writer 造成 TOCTOU。
4. Factory rebuild，等待 Space repo SHA 与 runtime SHA 等于新的 wrapper commit。
5. 使用 trusted verifier 完成 surface、capability、双层 auth 与 candidate source SHA smoke。

若 sync 已取得 rollback point，而 sync/rebuild/post-smoke 任一阶段失败：

- workflow 以 forward commit 恢复 prior revision 的四个受管文件，并再次 factory rebuild；
- 恢复后的 repo/runtime SHA 等于新的 rollback commit，health/readiness `source_sha` 等于
  `prior_souwen_ref`；不会 force-rewrite 历史；
- 如果发现未知外部 writer、恢复/rebuild/readback 失败，或没有可区分的 rollback commit，
  workflow 调用 `pause_space` 并验证 `PAUSED`；
- 原 promotion 仍保持失败，rollback 成功不能把失败验收伪装为 PASS。

GitHub Actions 的 cancel、runner 丢失或平台故障不能保证 rollback job 一定启动，因此失败通知
仍是人工 hard stop：先只读核对 Space repo/runtime/source 三段状态，再决定恢复或保持 paused。

## 必测入口

| 类别 | 地址 / 路径 | 验收目的 |
|---|---|---|
| 存活 | `/health` | 版本一致，`source_sha == candidate_sha` |
| 就绪 | `/readiness` | registry/config 可加载，source SHA 与 health 一致 |
| API schema | `/openapi.json` | title/version 与暴露策略正确 |
| API 文档 | `/docs` | Swagger UI 可按策略访问 |
| 管理面板 | `/panel` | 单文件前端 HTML 可返回 |
| 鉴权 | `/api/v1/whoami` | 双层 token 获得 admin；缺应用 token 不得为 admin |
| 控制面 | `/api/v1/admin/config`、`http-backend`、`warp`、`sources/config` | 可读、脱敏，修改型 smoke 能恢复原状态 |
| Doctor/Plugins | `/api/v1/admin/doctor`、`plugins` | 静态状态与插件表可读取 |

完整 capability smoke 会临时修改并恢复 HTTP backend/WARP 状态。外部搜索源受上游风控、出口
IP 和速率限制影响；报告中的 `WARN` 是带时间戳观测，不是永久可用承诺。

## 本地复现与失败处理

- API/CLI：`python scripts/ci/run_profile.py --profile pro-cli --profile basic-cli`。
- Docker：按 digest 拉取 base image，使用完整 SHA 重建 `cloud/hfs` context；没有 Docker daemon
  的机器不能把该层标为已验证。
- PR preflight 失败：修代码、测试或 wrapper，不直接触发远端 promotion。
- Promotion 前 rollback-point 检查失败：先人工建立可信 immutable baseline，不允许跳过检查。
- Auth smoke 失败：分别核对 private edge READ token 与 SouWen admin password，不把两个 token
  合并，也不临时开启 `SOUWEN_ADMIN_OPEN`。
- 自动 rollback/pause 失败：保持发布 No-Go，按 run 中记录的 prior SHA 做人工恢复并完整回读。
