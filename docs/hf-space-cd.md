# Hugging Face Space CD 与验收

本文说明 SouWen 的 Hugging Face Space 本地预检、受控 promotion、访问鉴权、provenance
与失败恢复边界。RC promotion 还必须满足
[Souwen v2rc5 发布候选门禁](./internal/rc-readiness-gates.md)。未经明确批准，不得同步 Space
仓库、factory rebuild、修改 secrets 或触发远端 smoke。

## 部署对象与访问边界

- 应用入口：<https://blueskyxn-souwen.hf.space/>
- 管理面板：<https://blueskyxn-souwen.hf.space/panel#/>
- OpenAPI 文档：<https://blueskyxn-souwen.hf.space/docs>
- Space 仓库：<https://huggingface.co/spaces/BlueSkyXN/SouWen>

目标 Space 必须在 promotion 前已是 `private=true`。这只证明 Space 仓库及其控制面可见性，
不能推导 App domain 的每条 HTTP surface 都被 Hugging Face edge 拒绝。当前部署允许匿名读取
Panel shell、Swagger、OpenAPI 和 probes；Data/Admin API 仍必须由独立的 SouWen application
credential 保护。部署后必须分别实测 surface、Data API 和 Admin API，不能用“Space 是 private”
替代负向鉴权证据。

`HF_TOKEN` 只用于 Space repo/settings/runtime 管理。`HF_SPACE_READ_TOKEN` 让 smoke 与可能启用
edge gate 的环境兼容；当前 App surface 即使不要求该 token，smoke 仍必须证明 edge-only 或完全匿名
请求都不能获得 admin。不要为了公开预览而开启 `SOUWEN_ADMIN_OPEN` 或匿名 Data API。

`/panel#/` 中的 `#` 是前端 hash router 片段，不会发送到服务端；服务端实际校验 `/panel`。
这些固定 URL 的可用性是运行时事实；平台策略变化后应重新读回 HTTP 状态。

## GitHub Actions 分层

`.github/workflows/deploy-hf-space.yml` 同时承担 local preflight 与 reusable promotion：

- `pull_request`：只运行本地 SDK/Server contract 与 HFS Docker smoke；不执行远程部署。
- 直接 `workflow_dispatch`：只运行本地 preflight，不写远端。
- 合入或 push `main`：**不会自动部署**。
- 远端 promotion：只能由 `.github/workflows/release-candidate.yml` 从当前 `main` control plane
  调用，并显式设置 `deploy_hfs=true`。

Central workflow 要求显式选择 `evidence_profile`；哨兵值 `select` 不执行。`release` profile
只接受四平台 PyInstaller Server bundle evidence；`deployment` profile 必须使用
`publish=false, deploy_hfs=true`，跳过 outer Server bundle release matrix，只生成不可发布的
deployment evidence。两种 profile 都继续运行非-binary gates；HFS reusable workflow 的 target
Server local preflight 不会被跳过。`deploy_hfs=true` 时，candidate 必须等于当前
`origin/main`；不能从未合入分支向持有 secrets 的部署 job 注入 verifier。Central caller 只在
HFS reusable call 上使用一次 `secrets: inherit`。这是同仓 reusable workflow 读取
environment-scoped secrets 的已知兼容处理（`actions/runner#4453`）；其他 reusable jobs 不得继承
secrets。这五个 environment secrets 不能同时声明为 required `workflow_call` secrets：GitHub 会在
called job 绑定 `environment: hf` 之前校验该 contract，因而把实际存在的 environment secrets 误判为
未传入。`deploy-hf-space.yml` 改为由 `environment: hf` 解析 `HF_TOKEN`、
`HF_SPACE_READ_TOKEN`、`SOUWEN_SMOKE_BEARER_TOKEN`、`SOUWEN_CONFIG_B64` 与
`UNIAPI_API_KEY`，并在 checkout 和任何 HF API 调用前按 secret 名称 fail fast，不输出值、
长度或前缀。

### Local preflight

| Job | 覆盖内容 | 边界 |
|---|---|---|
| `Resolve deploy eligibility` | 解析入口与 candidate contract | direct dispatch 不具备远端写资格 |
| `SDK and Server contracts` | `sdk-contract` + `server-contract` profiles | 验证 generated Python/TypeScript SDK 与本地 Server contract；不证明外部源在线 |
| `HF Space Docker surface smoke` | exact SHA 双进程启动、target/Worker readiness、docs/panel、49266 未发布 | 本地容器，不是 live Space |

`server-contract` 通过明确的 Server runtime leaf extras 安装所需实现；这不是新的
product tier 或 package matrix。

HFS Docker build 必须传 `SOUWEN_REF=<40位 candidate SHA>`。Dockerfile 的全零模板、短 SHA、
分支名和 moving `main` 都 fail closed；detached checkout 会把 SHA 写入
`/app/runtime.source.sha`，由 `/health.source_sha` 与 `/readiness.source_sha` 回读。
镜像无条件安装原生 Playwright Chromium；不提供额外 browser-fetch 产品入口。Supervisor 必须先验证
Worker readiness，再启动 API。

### 本地明文事实源

SouWen 当前采用 HFS v2.1 draft registry；正式公开基线仍为 v2.0。Tracked
`hfs-dev.toml` 只登记名称与路径，不保存真实值。本地事实源分为：

| 路径 | 权限 | 责任 |
|---|---:|---|
| `.env` | `0600` | env 值、控制凭据和三个受管 Space Secret 的本地值；不得提交 |
| `local/credentials/souwen-hfs.yaml` | `0600` | `SOUWEN_CONFIG_B64` 对应的可直接阅读原始 YAML；不得提交 |

`local/credentials/` 必须为 `0700`，两个文件都必须是普通文件且非 symlink。修改 HFS runtime
配置时先修改原始 YAML，再临时生成 Base64 并更新获批的本地/GitHub Secret source；不得把
Base64、Space Secret、远端 URL 或 CLI 登录状态当作唯一事实源。Registry-only sentinel 继续在
读取这些本地值和联网前拒绝通用 `hf_space_sync.py diff/push/pull`。

## Edge compatibility 与 application auth

当 Hugging Face edge 需要 token 时，它占用标准 `Authorization: Bearer <HF token>`。SouWen
application token 必须走独立的 `X-SouWen-Token`；即使当前 preview surface 匿名可读，也保留
两个职责不同的 workflow secrets，禁止让 write credential 充当应用密码：

| Secret | 用途 | 请求通道 |
|---|---|---|
| `HF_TOKEN` | 写 Space repo、restart/pause runtime | 仅 HFS 管理 API；需要 write 权限 |
| `HF_SPACE_READ_TOKEN` | 兼容可能启用的 private edge | `Authorization: Bearer ...`；目标权限只需 READ |
| `SOUWEN_SMOKE_BEARER_TOKEN` | SouWen 应用 admin password | `X-SouWen-Token: ...` |
| `SOUWEN_CONFIG_B64` | 与 Space 同源的 RC5 配置；promotion 前验证 exact 一个 LLM Search Provider、gateway 结构与一次 single-attempt live evidence | 仅 workflow 内存/临时文件预检；不输出配置值，post-deploy 仍重新验证 HFS runtime |
| `UNIAPI_API_KEY` | RC5 UniAPI gateway credential | workflow 将其写入同名 Space Secret；只回读 Secret 名称，不读取或记录值 |

SouWen 仍以标准 `Authorization: Bearer <password>` 作为普通部署的首选应用鉴权。只有上游
代理已经占用 `Authorization` 时才使用 `X-SouWen-Token`；显式 custom header 优先，若其值
无效，不会回退到另一个 header。远端必须删除/关闭 `SOUWEN_ADMIN_OPEN`，配置真实
`SOUWEN_ADMIN_PASSWORD`，并让 `SOUWEN_SMOKE_BEARER_TOKEN` 与其一致。

Post-deploy harness 从 central workflow 的受信 `verifier_sha` checkout 运行，不执行 candidate
checkout 中的 secret-bearing 脚本。验收同时证明：

1. 携带 `HF_SPACE_READ_TOKEN` 时 surface 可按当前 edge 策略访问。
2. 携带独立 SouWen token 时 `/api/v1/whoami` 为 `role=admin && admin_open=false`。
3. 只通过 HF edge 或完全匿名、不提供 SouWen token 时，不得获得 admin 或访问 Data/Admin API。

## Provenance 三段模型

三个 SHA 不能混为一谈：

| 字段 | 含义 | 必须满足 |
|---|---|---|
| `candidate_sha` / `source_sha` | SouWen 源码 commit | health/readiness `source_sha == candidate_sha` |
| `space_repo_sha` | Space wrapper 仓库 commit | 该 revision 的 Dockerfile 精确 pin `SOUWEN_REF=<candidate_sha>` |
| `runtime.raw.sha` | HF 当前运行的 wrapper revision | `runtime.raw.sha == space_repo_sha` |
| `health/readiness.wrapper_sha` | deployment 注入的 wrapper identity | 必须等于 `space_repo_sha`，但不能替代 HF API readback |

`RUNNING`、版本相同或 Space repo SHA 单独都不能证明 candidate 已接管。Manifest 应分别保存
`hfs.repo_sha`、`hfs.runtime_sha` 与 `hfs.source_sha`，不能要求 wrapper SHA 等于 SouWen source
SHA。

## Promotion 与恢复事务

远端 promotion 依次执行：

1. 在任何 wrapper mutation 前只读旧 runtime；仅接受 `RUNNING` 或 `SLEEPING` 且旧 Space
   repo SHA 与 runtime SHA 相等的稳定状态。`PAUSED`、error state 或 SHA 漂移必须在写入前
   fail closed，不通过提前 restart 改变旧 runtime 状态。
2. 记录 `prior_space_commit_sha`、`prior_runtime_commit_sha`、`prior_souwen_ref`。旧部署没有
   immutable source pin 时，在写入前停止，不能回退到 floating `main`；同时记录
   `prior_runtime_stage` 供 manifest 和恢复审计。
3. rollback point 稳定后，workflow 先只读 Secret 名称并拒绝任何未登记名称，再从 exact candidate
   生产 runtime assembly 对 `SOUWEN_CONFIG_B64` **显式选中的唯一 LLM Search Provider**执行一次
   `max_results_per_provider=1`、single-attempt live request。它不 retry、不遍历第二个 Provider、不自动
   切换 model，也不输出 gateway、credential 或 raw upstream body。配置 loader 运行在隔离环境中：
   gateway `api_key` 只允许 literal 或 exact `${UNIAPI_API_KEY}`，`base_url` 必须是 literal HTTP(S)
   URL；GitHub runner 的其他 token、`HOME` 或 `SOUWEN_*` 不能参与解析。这是获授权 promotion 的一次付费
   pre-mutation gate；任一失败都发生在 mutation marker 前，因此原健康 Space 保持不变且不 pause。
   两个 preflight 完成后、第一次写入前，workflow 才写出 `settings_mutation_started=true` 事务标记，
   将 `SOUWEN_SMOKE_BEARER_TOKEN` 映射为 Space `SOUWEN_ADMIN_PASSWORD`，并同步
   `SOUWEN_CONFIG_B64`、`UNIAPI_API_KEY`。写入后名称集合必须精确等于 `hfs-dev.toml` 中的三个受管
   名称；不删除未知 Secret，也不输出值、长度、hash 或前缀。
4. 只同步受管的四个 wrapper 文件；diff 固定读取 prior revision，`create_commit` 使用
   `parent_commit=<prior_space_commit_sha>` 防止外部 writer 造成 TOCTOU。取得新 commit 后，
   transaction 写入并立即 readback `SOUWEN_WRAPPER_SHA=<space_commit_sha>` Space variable。
5. Factory rebuild，等待 Space repo SHA 与 runtime SHA 等于新的 wrapper commit。
6. 使用 trusted verifier 完成 surface、target capability、edge/application auth 与 candidate/source/
   wrapper SHA smoke。Required checks 固定覆盖 Search、LLM Search 与 immutable Fetch；readiness
   另行证明 Browser Worker ready 且 source SHA 一致。Pre-mutation provider gate 不能替代 HFS egress、
   application assembly 或 post-deploy capability smoke。普通 PR/main CI 不做付费 LLM Search live call；
   只有显式 HFS promotion 或 paused recovery 才执行。

Space Secret 是 write-only：workflow 能读回名称，不能捕获旧值。因此
`settings_mutation_started=true` 一旦完成，
任何 sync/rebuild/post-smoke 失败都不能安全地自动恢复成“旧 wrapper + 旧 settings”。失败路径必须：

- 调用 `pause_space` 并验证 `PAUSED`，避免旧代码与新/部分 settings 组合继续对外运行；
- 保留 prior repo/runtime/source snapshot 和失败 run，供受控 operator recovery 使用；
- 从获批的安全 Secret source 恢复相互匹配的 settings，再选择 prior 或 corrected wrapper，factory
  rebuild 后重新执行完整 surface/capability/provenance smoke；
- 保持原 promotion 为失败，暂停成功不能把失败验收伪装为 PASS。

这是一条 fail-closed containment 路径，不是自动 rollback。只调整 Secret 与 wrapper 的写入顺序
无法解决 write-only prior values 缺失。GitHub Actions cancel、runner 丢失或平台故障也不能保证
containment job 一定启动，因此失败通知仍是人工 hard stop：先只读核对 Space repo/runtime/source
与 settings names，再决定恢复，未完成恢复前保持 paused。

需要从已知失败 transaction 前向恢复时，只能从 current `main` 手工 dispatch
`.github/workflows/recover-hf-space.yml`。该 workflow 不是发布入口；它要求 repository owner 同时是
actor/triggering actor，并精确绑定 source run ID、paused wrapper/source SHA、failed candidate SHA、prior
wrapper/source SHA；validate 与 mutation marker 前都会 fail-close 证明目标 RC tag/Release 尚不存在。
Source run 可以是 containment 成功且 publish skipped 的 failed release，也可以是 validate 成功、完整
transaction run-name receipt 匹配且再次 containment 的 failed recovery。Reusable workflow 在 mutation
marker **之前**先上传 `souwen-hfs-transaction-intent-v1`，绑定 run/attempt、candidate、prior/current
wrapper、source pin 与 inputs；intent 上传失败时不得写 Secret。Primary 或 retry containment 后另上传
outcome evidence，但 recovery 只依赖 mutation 前已持久化的 intent、Actions jobs provenance 与 live paused
topology，因此 outcome runner/upload 失败不会锁死恢复入口。所有 release/recovery source 和当前 dispatch
都只接受 `run_attempt=1`，禁止 rerun 复用 run ID。历史 run `30545216223` 早于 intent，只允许代码中一次性
固定的 exact run/candidate/paused/prior SHA contract，不能泛化为其他 legacy run。
Reusable HFS workflow 验证 Space 仍为 private/`PAUSED`，并只接受两个状态：Secret 写入后 wrapper 尚未
前移的 `settings-only` 拓扑，或 paused wrapper **直接**继承 prior wrapper 且 pin failed candidate 的
`wrapper-advanced` 拓扑。随后从获批 GitHub `hf` environment Secret source 重写完整 settings，以当前
paused wrapper 为并发保护 parent 创建新 candidate wrapper。Recovery 先用普通 restart 建立“已离开
`PAUSED`”的有界 barrier，立即执行一次 factory reboot；它不等待第一次 build 完成，因此仍只有一次
完整 900 秒 runtime takeover wait。之后再完成完整
surface/capability/provenance smoke；任一步失败仍会重新 pause，且可用新失败 recovery receipt 再次前向
恢复。`release-candidate.yml` 与 recovery 使用同一全局 concurrency group，锁覆盖标准 run 的 HFS、
assemble 与 publish 全阶段，避免旧 evidence 与新 runtime 交叉发布。Recovery 成功只恢复到稳定 runtime，
不生成 tag/Release，也不能替代之后新的标准 `release-candidate.yml` publish run。

Recovery 的 `prior_space_commit_sha`/`prior_souwen_ref` 仅表示已验证的 transaction-parent ancestry；当前
Space 为 `PAUSED` 时无法把该 parent 冒充 runtime readback，因此 `prior_runtime_commit_sha` 与
`prior_runtime_stage` 明确留空。只有普通 promotion 从稳定 `RUNNING`/`SLEEPING` 捕获的值才属于 prior
runtime evidence。

## 必测入口

| 类别 | 地址 / 路径 | 验收目的 |
|---|---|---|
| 存活 | `/healthz`、`/health` | version/source/wrapper/rollout 一致，API process 可响应 |
| 就绪 | `/readyz`、`/readiness` | target config/Provider 可用，`browser_worker=ready` 且 Worker source 匹配 |
| API schema | `/openapi.json` | title/version 与暴露策略正确 |
| API 文档 | `/docs` | Swagger UI 可按策略访问 |
| 管理面板 | `/panel` | 单文件前端 HTML 可返回 |
| 鉴权 | `/api/v1/whoami` | 应用 token 获得 admin；edge-only/匿名请求不得为 admin |
| 控制面 | `/api/v1/admin/config`、`/api/v1/admin/ping` | 只读、脱敏且受 admin auth 保护 |
| Doctor | `/api/v1/admin/doctor` | 静态状态可读取 |

完整 capability smoke 不修改运行时配置；它只读 Provider catalog，并真实调用一个可用的
Search Provider、已配置的 LLM Search Provider 与 immutable Fetch 目标。任一 required check
失败即 promotion 失败。

## 本地复现与失败处理

- Target Server：`python scripts/ci/run_profile.py --profile server-contract`。
- Docker：按 digest 拉取 base image，使用完整 SHA 重建 `cloud/hfs` context；没有 Docker daemon
  的机器不能把该层标为已验证。
- PR preflight 失败：修代码、测试或 wrapper，不直接触发远端 promotion。
- Promotion 前 rollback-point 检查失败：先人工建立可信 immutable baseline，不允许跳过检查。
- Auth smoke 失败：分别核对可选 edge READ token 与 SouWen admin password，不把两个 token合并，
  也不临时开启 `SOUWEN_ADMIN_OPEN`。
- 自动 containment/pause 失败：保持发布 No-Go，按 run 中记录的 prior SHA 和获批 Secret source
  做人工恢复并完整回读。
