# 部署

本文记录仓库内可直接复用的部署方式。更多 Hugging Face Space 细节见
[hf-space-cd.md](./hf-space-cd.md)，WARP 细节见
[warp-solutions.md](./warp-solutions.md)。

发布候选的容器、远端 CI、HFS promotion 和资产验收必须遵循
[Souwen v2rc5 发布候选门禁](./internal/rc-readiness-gates.md)。该门禁文档只固定规则；
candidate SHA、run URL、checksum、SBOM/provenance 和执行结论写入候选专属的
`release-manifest.json` artifact，不提交运行结果到仓库。

## Central RC workflow

`.github/workflows/release-candidate.yml` 是唯一 release orchestrator。它必须从当前
`main` control plane 运行，输入为 40 位 `candidate_sha` 与完整 PEP 440 prerelease
`version`，并显式选择 `evidence_profile`：

```bash
gh workflow run release-candidate.yml \
  --ref main \
  -f candidate_sha="$(git rev-parse HEAD)" \
  -f version=2.0.0rc5 \
  -f evidence_profile=release \
  -f publish=false \
  -f deploy_hfs=false
```

`evidence_profile` 必须显式选择，默认哨兵值 `select` 会 fail closed：

- `release` 运行 source、clean install、Panel、container，以及精确四个平台的
  PyInstaller Server bundle gate；package job 同时生成 immutable
  `souwen-openapi-2.0.0rc5.json`。Assembler 只接受四个固定名称的 archive、对应的四份
  target-native smoke、同 candidate inventory 和一致的 OpenAPI checksum。
- `deployment` 必须同时使用 `deploy_hfs=true, publish=false`。它跳过外层 `server-bundles`
  release job，但保留全部非 binary gate、HFS reusable workflow 的 target Server local preflight、
  live promotion、fail-closed containment 和 readback，产出不可发布的
  `deployment-evidence-*` artifact。Assembler 还会解析 surface/capability JSON，要求 target
  runtime、Browser Worker readiness、Search、LLM Search 与 immutable Fetch 全部为 `PASS`；
  报告文件仅存在不构成通过。

轻量 HFS promotion 使用：

```bash
gh workflow run release-candidate.yml \
  --ref main \
  -f candidate_sha="$(git rev-parse HEAD)" \
  -f version=2.0.0rc5 \
  -f evidence_profile=deployment \
  -f publish=false \
  -f deploy_hfs=true
```

`deploy_hfs=true` 或 `publish=true` 只允许 `candidate_sha == origin/main`，并要求受保护的
`hf` / `release` environment；`publish=true` 还强制 `evidence_profile=release`、
`deploy_hfs=true` 且 live promotion 已通过。

`build-pyinstaller-server.yml` 是 central release 的唯一 active binary builder；它只上传
workflow artifacts，不创建 Release。旧 `build-pyinstaller.yml` 与 `build-nuitka.yml`（24 个
CLI/Nuitka binary 合同）已随 CI 分档改造删除；central workflow 的 manifest 继续 fail-closed
拒绝 `souwen-linux-*`、`souwen-macos-*`、`souwen-windows-*`、`souwen-nuitka-*` 等旧 artifact
前缀，旧 binary 不得出现在 RC5 manifest 或 Release assets。Tag 与 prerelease 只能由 central
workflow 的 publish job 创建。`publish=true` 只在 owner-approved RC5 exact-main release 中使用。

## RC5 PyInstaller Server bundle

`.github/workflows/build-pyinstaller-server.yml` 是 RC5 四平台 Server bundle builder。它既可由
`workflow_dispatch` 对一个 40 位 immutable candidate做独立 proof，也可由 central release
workflow 通过 `workflow_call` 调用。Builder 不创建 tag、Release或HFS deployment。
Candidate checkout只提供待构建源码；target-native smoke action另从 `github.workflow_sha`
checkout trusted verifier，aggregate要求精确required-check集合全部 `PASS`，不能信任candidate
自行生成的summary字段。

正式 archive 名称固定为：

```text
souwen-server-2.0.0rc5-linux-amd64.tar.gz
souwen-server-2.0.0rc5-linux-arm64.tar.gz
souwen-server-2.0.0rc5-macos-arm64.tar.gz
souwen-server-2.0.0rc5-windows-amd64.zip
```

Archive 内部统一使用 `souwen-server/` 目录；Windows executable 为
`souwen-server.exe`，其余平台为 `souwen-server`。同目录包含 `ms-playwright/` 和
`runtime.source.sha`。这是 Browser Worker运行所需的 deployment unit，不是一个仅改名的旧 CLI
binary。

默认入口：

```bash
./souwen-server/souwen-server --host 127.0.0.1 --port 49265
```

Server 始终运行 target-only v2；部署不需要单独的 rollout 环境开关。
Supervisor 在 frozen runtime中用同一个 executable 的隐藏 `--internal-role worker|api` 派生两个
子进程，并通过仅由 Supervisor设置的内部环境标记限制直接调用。源码/container路径继续使用
现有 Python module child commands，避免改变 HFS runtime合同。
Windows bundle同时启用 PyInstaller embedded Python UTF-8 mode；Windows Supervisor把收到的
`SIGBREAK` 映射为 child process group可接受的 `CTRL_BREAK_EVENT`，再执行有界shutdown。

每个平台必须安装并打包 Playwright Chromium，设置 bundle-local
`PLAYWRIGHT_BROWSERS_PATH`，解压最终 archive 后运行 target-native smoke。Linux bundle的支持
基线是构建它的 GitHub-hosted Ubuntu runner ABI；目标主机仍需具备 Chromium运行所需的系统
libraries。RC5 不把一个不含 browser runtime的裸 executable描述为 self-contained bundle。

## Docker

```bash
export SOUWEN_ADMIN_PASSWORD=change-me
export SOUWEN_USER_PASSWORD=change-me-user
docker build -t souwen .
docker run -p 8000:49265 \
  -e SOUWEN_ADMIN_PASSWORD \
  -e SOUWEN_USER_PASSWORD \
  -v "$PWD/souwen.yaml:/app/souwen.yaml:ro" \
  -v souwen-data:/app/data \
  souwen
```

`/app/souwen.yaml` 是容器工作目录下的应用配置真源；`/app/data` 只承载 WARP/runtime
persistence。把宿主机配置目录只挂到 `/app/data` 不会让 config loader 读取该文件。只使用
环境变量时可以省略 `souwen.yaml` mount，但仍可保留独立 data volume。

启动后检查：

```bash
curl http://localhost:8000/healthz
curl -H "Authorization: Bearer $SOUWEN_USER_PASSWORD" \
  http://localhost:8000/api/v1/providers
```

Release/container 构建应注入 `SOUWEN_SOURCE_SHA=<40位candidate SHA>` 或
`runtime.source.sha`；`/healthz` 与 `/readyz` 会以 `source_sha` 回读。普通本地源码运行
允许为 `null`，但 RC container gate 要求非空且与 candidate SHA 完全一致。

## RC 容器 provenance

Root 镜像复制当前 checkout，RC 构建必须显式注入同一 checkout 的 SHA：

```bash
CANDIDATE_SHA="$(git rev-parse HEAD)"
docker build \
  --build-arg SOUWEN_SOURCE_SHA="${CANDIDATE_SHA}" \
  -t "souwen:${CANDIDATE_SHA}" .
```

HFS / ModelScope wrapper 会从 Git remote 按 SHA 拉源码，必须传远端可达的完整 40 位 commit；
默认全零模板会 fail closed，分支名、短 SHA 和全零值都不能构建：

```bash
docker build -f cloud/hfs/Dockerfile \
  --build-arg SOUWEN_REF="${CANDIDATE_SHA}" \
  -t "souwen-hfs:${CANDIDATE_SHA}" cloud/hfs
docker build -f cloud/modelscope/Dockerfile \
  --build-arg SOUWEN_REF="${CANDIDATE_SHA}" \
  -t "souwen-modelscope:${CANDIDATE_SHA}" cloud/modelscope
```

- Root 把 build arg 写入 `/app/runtime.source.sha`；HFS 从 detached checkout 写入同一路径；
  ModelScope 写入 `/home/user/app/runtime.source.sha`。
- RC5 HFS 使用 `deploy/process/supervisor.py` 管理两个进程：Browser Worker 只绑定
  `127.0.0.1:49266`，通过 authenticated readiness 后 API 才绑定 `0.0.0.0:49265`。HFS 只
  `EXPOSE/app_port` 49265；不得为 Worker 添加 host port mapping。
- Supervisor 从 `runtime.source.sha` 解析 source SHA，使用 source-owned 默认配置时生成
  `source-<candidate_sha>` config revision，并把同一 source/config/token 传给两个 child。
  HFS transaction 将实际 Space commit 写入受管的 `SOUWEN_WRAPPER_SHA` variable；该值只用于
  provenance，不替代 `runtime.raw.sha` 的外部 readback。
- Root/HFS 显式使用 `WARP_DATA_DIR=/app/data`、`WARP_RUNTIME_BIN_DIR=/app/data/bin`；
  ModelScope 使用 `/home/user/app/data` 与 `/home/user/app/data/bin`。entrypoint 的 `PATH`
  注入和 Python `WarpManager` 都从这两个环境变量派生，持久卷与动态安装目录必须挂到同一
  platform-specific data root。
- 三个 Dockerfile 的 base image 使用 digest pin；WARP 下载必须通过
  `scripts/warp-checksums.txt`。更新版本时必须同步 pin/checksum 及测试，不能临时跳过校验。

## 本地服务

```bash
pip install -e ".[server,tls,web,robots,scraper]"
SOUWEN_ADMIN_PASSWORD=change-me uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
```

## Hugging Face Spaces

仓库的 `cloud/hfs/` 保存 Space 部署资源。部署前先本地跑：

```bash
PYTHONPATH=src python3 scripts/ci/run_profile.py --profile server-contract
```

`server-contract` 是本地部署前的 Server contract 验证。`sdk-contract` 验证 frozen
target-only OpenAPI、generated Python sync/async SDK 与 Panel TypeScript SDK 的可重复生成、
API-major preflight、auth/error/request-ID 和 clean import。Panel 的 TypeScript runtime
contract 继续由 Vitest 覆盖。Server runtime 通过明确 leaf extras 安装，不使用 product tier
或 edition package matrix。

PR 与直接运行 `HF Space CD` 只执行 local preflight。远端 promotion 只能由 central RC
workflow 显式传 `deploy_hfs=true`，并按 [hf-space-cd.md](./hf-space-cd.md) 完成 edge compatibility、
application admin、repo/runtime/source SHA 与 settings-aware containment 验收。

## 运行时保护

- 生产环境设置 `SOUWEN_ADMIN_PASSWORD`；
- 需要开放搜索时设置 `SOUWEN_USER_PASSWORD`，或明确启用 `SOUWEN_GUEST_ENABLED=true`；
- 反向代理后方设置 `SOUWEN_TRUSTED_PROXIES`；
- 需要关闭 OpenAPI 页面时设置 `SOUWEN_EXPOSE_DOCS=false`；
- 高风险网页源建议配置 WARP 或显式代理。
