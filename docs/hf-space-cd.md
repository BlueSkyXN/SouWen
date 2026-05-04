# Hugging Face Space CD 与验收

本文档说明 SouWen 在 Hugging Face Space 上的自动部署、PR 本地预检和部署后验收边界。

## 部署对象

- 远端应用入口：<https://blueskyxn-souwen.hf.space/>
- 管理面板入口：<https://blueskyxn-souwen.hf.space/panel#/>
- OpenAPI 文档入口：<https://blueskyxn-souwen.hf.space/docs>
- Space 仓库：<https://huggingface.co/spaces/BlueSkyXN/SouWen>

`/panel#/` 中的 `#` 是前端 hash router 片段，不会发送到服务端；服务端实际校验 `/panel` 是否返回前端 HTML。`/docs` 与 `/openapi.json` 用于确认 API 文档和 schema 暴露状态。

## GitHub Actions 分层

所有 Hugging Face Space 相关门禁和部署都收敛在 `.github/workflows/deploy-hf-space.yml`，工作流名称为 `HF Space CD`。它支持 `pull_request`、`main` 分支 `push` 和 `workflow_dispatch` 三类入口：

### PR / Push 本地预检

本地预检 job 不依赖 Hugging Face secrets，目标是提前拦截本地可复现的问题。它们在同一个 workflow 中并行运行：

| Job | 覆盖内容 | 说明 |
|---|---|---|
| `Resolve deploy eligibility` | `main` push / 手动触发的部署路径判断 | 文档或测试-only 变更仍跑本地预检，但不会触发远端部署 |
| `API surface and source CLI` | `tests/test_server`、`tests/test_hf_space_smoke.py`、源码 CLI 真实进程 | 覆盖服务端基础路由、smoke 脚本契约和 `python cli.py ...` / `python -m souwen ...` |
| `PyInstaller CLI smoke` | Linux CLI-only 单文件构建后执行 | 验证 PyInstaller 产物至少能完成帮助、版本、sources、config show 等非网络命令 |
| `HF Space Docker surface smoke` | 使用 `cloud/hfs/Dockerfile` 从当前 PR head SHA 构建并本地启动容器 | 验证 `/health`、`/readiness`、`/docs`、`/panel` 和核心 admin API surface |

这层只验证本地 API/CLI/容器启动契约，不代表外部搜索源在远端网络环境中稳定可用。

### Main 部署

远端部署 job 只在 `main` 分支运行，并且必须等待本地预检 job 全部通过：

1. `Sync HFS wrapper files`：同步 `cloud/hfs/` wrapper 文件到 Hugging Face Space 仓库，并输出预期 SouWen 版本。
2. `Factory rebuild Space`：触发 Space factory rebuild，并等待 Space runtime 进入 `RUNNING`。
3. `Post-deploy smoke matrix` / `surface`：访问真实远端地址，执行 `--surface-only`，快速确认页面入口和 API surface。
4. `Post-deploy smoke matrix` / `capability`：访问真实远端地址，执行完整部署后 capability smoke，覆盖 zero-key 搜索、fetch、archive、WARP/backend 矩阵等能力。
5. 两个 smoke job 分别上传 Markdown/JSON 报告 artifact：`hf-space-cd-surface-report` 和 `hf-space-cd-capability-report`。

部署后 `surface` 与 `capability` 两个 smoke 入口可在 factory rebuild 完成后并行运行。完整 capability smoke 会修改并恢复 HTTP backend / WARP 状态，因此这部分保持单 job 单写者，避免多个矩阵 job 同时改同一个线上实例。外部搜索源受上游风控、出口 IP、速率限制影响，报告中的 `WARN` 应理解为当次观测结果，不应写成固定可用承诺。

## 必测入口

| 类别 | 地址 / 路径 | 验收目的 |
|---|---|---|
| 存活 | `/health` | 进程可访问，版本与 `pyproject.toml` 一致 |
| 就绪 | `/readiness` | 本地配置和 source registry 可加载 |
| API schema | `/openapi.json` | OpenAPI title/version 正确 |
| API 文档 | `/docs` | Swagger UI 可打开 |
| 管理面板 | `/panel`（用户访问 `/panel#/`） | 前端 HTML 可返回 |
| 鉴权状态 | `/api/v1/whoami` | 当前部署 admin 访问状态明确 |
| 配置 | `/api/v1/admin/config` | 关键配置可读且敏感字段脱敏 |
| HTTP 后端 | `/api/v1/admin/http-backend` | 能取得原始 backend 快照，后续矩阵测试才允许修改并恢复 |
| WARP | `/api/v1/admin/warp`、`/warp/modes`、`/warp/config`、`/warp/components` | 能读取 WARP 状态、可用模式和组件信息 |
| 数据源配置 | `/api/v1/admin/sources/config`、`/sources/config/openalex` | registry 与频道配置可读 |
| Doctor | `/api/v1/admin/doctor` | 源健康摘要可生成 |
| Plugins | `/api/v1/admin/plugins` | 插件列表 API 可读 |

## Docker 是否需要拉取远端镜像

当前 PR 预检不拉取线上镜像，而是用 `cloud/hfs/Dockerfile` 从当前 PR head SHA 构建临时镜像。这样可以验证本次 check 对应的固定源码状态、wrapper、panel 构建和 Python 依赖组合，避免分支名在 workflow 运行期间移动导致验证对象不准确。线上 Space 的最终结果仍以 `main` 合入后的真实 factory rebuild 和远端 smoke 为准。

## 本地复现策略

- API 与源码 CLI：直接运行 `pytest tests/test_server tests/test_hf_space_smoke.py`，再执行 `python cli.py --help`、`python cli.py --version`、`python cli.py sources`、`python cli.py config show`、`python cli.py config backend`、`python -m souwen --help`。
- PyInstaller CLI：使用干净 virtualenv 复现，避免全局 Python 环境把 unrelated 包带入分析。CLI-only 构建需要固定 `setuptools<82`，并显式 `--collect-submodules=rich._unicode_data`，否则单文件包可能在启动或 Rich help 输出时失败。
- Docker / `act`：这层依赖 Docker daemon，会拉取 `node:*` 和 `python:*` 基础镜像，并按 PR head SHA 重新构建 HFS 镜像。没有 Docker 的本机不应把该层视为已验证；以 GitHub-hosted runner 的 `HF Space Docker surface smoke` 为准。

## 失败处理

- PR 本地预检失败：优先修代码、测试或 wrapper，不应直接重跑远端部署。
- 部署同步或 factory rebuild 失败：检查 `HF_TOKEN`、Space 仓库权限和 Hugging Face runtime 日志。
- 远端 smoke 在 `admin/http-backend-get` 失败：视为控制面回归，因为后续矩阵无法安全恢复原始状态。
- 远端 zero-key 源 `WARN`：先看报告中的 source/backend/WARP 组合，再判断是上游波动还是代码回归。
