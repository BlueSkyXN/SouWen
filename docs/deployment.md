# 部署

本文记录仓库内可直接复用的部署方式。更多 Hugging Face Space 细节见
[hf-space-cd.md](./hf-space-cd.md)，WARP 细节见
[warp-solutions.md](./warp-solutions.md)。

发布候选的容器、远端 CI、HFS promotion 和资产验收必须遵循
[v2.0.0rc1 发布候选门禁](./internal/rc-readiness-gates.md)。该门禁文档只固定规则；
candidate SHA、run URL、checksum、SBOM/provenance 和执行结论写入候选专属的
`release-manifest.json` artifact，不提交运行结果到仓库。

## Central RC workflow

`.github/workflows/release-candidate.yml` 是唯一 release orchestrator。它必须从当前
`main` control plane 运行，输入为 40 位 `candidate_sha` 与完整 PEP 440 prerelease
`version`：

```bash
gh workflow run release-candidate.yml \
  --ref main \
  -f candidate_sha="$(git rev-parse HEAD)" \
  -f version=2.0.0rc1 \
  -f publish=false \
  -f deploy_hfs=false
```

默认 `publish=false`、`deploy_hfs=false` 只运行 source、clean install、Panel、container、
external smoke、PyInstaller/Nuitka 和 bundle/attestation gate，产出 RC-ready evidence bundle；
不创建 tag、GitHub Release，也不写 HFS。`deploy_hfs=true` 或 `publish=true` 只允许
`candidate_sha == origin/main`，并要求受保护的 `hf` / `release` environment；
`publish=true` 还强制 `deploy_hfs=true` 且 live promotion 已通过。

PyInstaller 与 Nuitka workflow 只是 builder。手动运行或 `v*` tag 触发时只上传 workflow
artifacts，不创建 Release；tag 与 prerelease 只能由 central workflow 的 publish job 创建。

## Docker

```bash
export SOUWEN_ADMIN_PASSWORD=change-me
export SOUWEN_USER_PASSWORD=change-me-user
docker build -t souwen .
docker run -p 8000:49265 \
  -e SOUWEN_ADMIN_PASSWORD \
  -e SOUWEN_USER_PASSWORD \
  -v ~/.config/souwen:/app/data \
  souwen
```

启动后检查：

```bash
curl http://localhost:8000/health
curl -H "Authorization: Bearer $SOUWEN_USER_PASSWORD" \
  http://localhost:8000/api/v1/sources
```

Release/container 构建应注入 `SOUWEN_SOURCE_SHA=<40位candidate SHA>` 或
`runtime.source.sha`；`/health` 与 `/readiness` 会以 `source_sha` 回读。普通本地源码运行
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
- Root/HFS 显式使用 `WARP_DATA_DIR=/app/data`、`WARP_RUNTIME_BIN_DIR=/app/data/bin`；
  ModelScope 使用 `/home/user/app/data` 与 `/home/user/app/data/bin`。entrypoint 的 `PATH`
  注入和 Python `WarpManager` 都从这两个环境变量派生，持久卷与动态安装目录必须挂到同一
  platform-specific data root。
- 三个 Dockerfile 的 base image 使用 digest pin；WARP 下载必须通过
  `scripts/warp-checksums.txt`；SuperWeb2PDF direct URL 带 `#sha256=` hash。更新版本时必须
  同步 pin/checksum 及测试，不能临时跳过校验。
- `WITH_WEB2PDF=1` 还需要验证 plugin entry point、fetch handler、Chromium 和 fixture PDF，
  仅完成 `pip install` 不构成 runtime PASS。

## 本地服务

```bash
pip install -e ".[edition-pro]"
SOUWEN_ADMIN_PASSWORD=change-me souwen serve --host 0.0.0.0 --port 8000
```

## Hugging Face Spaces

仓库的 `cloud/hfs/` 保存 Space 部署资源。部署前先本地跑：

```bash
PYTHONPATH=src SOUWEN_PLUGIN_AUTOLOAD=0 \
  python3 scripts/ci/run_profile.py --profile pro-cli --profile basic-cli
```

旧 `server` / `minimal` 名称仍作为过渡 alias 可用，新文档和新 workflow 优先使用
`pro-cli` / `basic-cli`。

PR 与直接运行 `HF Space CD` 只执行 local preflight。远端 promotion 只能由 central RC
workflow 显式传 `deploy_hfs=true`，并按 [hf-space-cd.md](./hf-space-cd.md) 完成 private edge、
应用 admin、repo/runtime/source SHA 与 rollback 事务验收。

## 运行时保护

- 生产环境设置 `SOUWEN_ADMIN_PASSWORD`；
- 需要开放搜索时设置 `SOUWEN_USER_PASSWORD`，或明确启用 `SOUWEN_GUEST_ENABLED=true`；
- 反向代理后方设置 `SOUWEN_TRUSTED_PROXIES`；
- 需要关闭 OpenAPI 页面时设置 `SOUWEN_EXPOSE_DOCS=false`；
- 高风险网页源建议配置 WARP 或显式代理。
