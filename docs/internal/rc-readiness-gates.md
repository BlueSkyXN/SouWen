# SouWen v2.0.0rc1 发布候选门禁

本文固定 `v2.0.0rc1` 的 Go / No-Go 规则、阈值和证据字段。它不是某次执行报告：
candidate SHA、run URL、checksum、测试计数和部署回读等运行结果不得写回本文件，
而应由发布流水线写入候选专属的 `release-manifest.json` 或
`deployment-manifest.json` artifact。

## 判定原则

- 所有 required gate 必须针对同一个 immutable `candidate_sha`；只要源码、lockfile、
  构建参数或生成产物变化，就必须创建新 candidate 并重跑受影响 gate。
- `PASS` 必须有原始 machine-readable evidence。终端摘要、人工描述、`RUNNING` 状态或
  “历史上通过”不能替代测试报告、run URL、checksum 和运行时回读。
- `WARN` 只适用于规则明确标注的高波动外部源；required check 不得通过重试、
  `continue-on-error`、空报告或 silent fallback 降级为 `WARN`。
- 任何 secret、token、Cookie、私有 URL userinfo 或客户数据不得进入 manifest、日志、
  SBOM、attestation、release note 或截图。
- 本文件和仓库只保存固定规则。候选执行结果、临时环境、coverage 数据、构建目录、
  browser cache 和 `release-manifest.json` 均不提交到 Git。

## Gate 分类

本文件定义 16 个 gate，其中 15 个是 **always-required**，`HFS promotion` 是 conditional：

- **Deployment-validated**：显式使用 `evidence_profile=deployment`、`publish=false`、
  `deploy_hfs=true`。除两个外层 release binary matrix 外的 common gates 与 HFS promotion
  全部 `PASS`；PyInstaller/Nuitka release matrix 为预期 `skipped`。该状态只证明候选的 HFS
  runtime，不是 RC-ready 或 publish-ready，产物必须命名为 `deployment-evidence-*` 且标记
  `publishable=false, binary_count=0`。
- **RC-ready**：除 HFS promotion 外的 15 个 gate 全部 `PASS`；HFS 为
  `required=false, status=NOT_RUN`。Central workflow 使用 `evidence_profile=release`、
  `publish=false, deploy_hfs=false`，只生成 evidence bundle，不创建 tag/Release、不写 Space。
- **Publish-ready**：RC-ready 加上 HFS promotion `PASS`；private edge、SouWen admin、
  wrapper/runtime/source provenance 和 rollback point 均有证据。只有该状态才允许
  `evidence_profile=release, publish=true`。

`release-candidate.yml` 必须从当前 `origin/main` 的 control-plane workflow 运行；任何
candidate code 执行前先做 immutable SHA、lineage 与 version static check。无 deploy/publish 的
RC-ready run 可以验证从 current main 派生的 candidate；任何 secret-bearing promotion/publish
要求 `candidate_sha == origin/main`。

## Gate definitions

### 1. Worktree

- 候选从预期 release ref 创建，local HEAD、remote candidate ref 和 manifest
  `candidate_sha` 完全一致。
- `git status --short` 为空；无未跟踪产物、未合并提交、stash 依赖或 submodule 漂移。
- 版本面均为 `2.0.0rc1`，生成物由正式命令生成，没有手改 generated artifact。

**Evidence**：`candidate_sha`、ref、tree hash、version readback、worktree-clean assertion。

### 2. Python 与冷启动性能

- 完整 `pytest tests/` 在规定 Python / OS matrix 全部通过；相对批准 baseline 没有新增
  非预期 skip / xfail。
- `ruff check src tests scripts tools` 和 `ruff format --check src tests scripts tools` 通过。
- Ubuntu Python 3.11 在干净安装环境中对每项启动 7 个独立冷进程，记录原始 7 次耗时并
  以 median 判定：package import `<= 1.5s`、registry catalog `<= 1.5s`、CLI help
  `<= 2.0s`、server import `<= 2.5s`。不得在同一解释器内循环伪装冷启动。

**Evidence**：pytest JUnit、skip/xfail diff、Ruff 输出、4 组原始耗时与 median、Python/OS。

### 3. Coverage

- 全量 Python coverage 不低于 **67.0%**。
- edition / feature matrix / doctor 的 targeted coverage 不低于 **90.0%**；targeted
  报告必须限定到对应模块，不能用全仓高覆盖稀释低覆盖文件。
- Coverage XML/JSON 的源码 SHA 必须等于 `candidate_sha`。

**Evidence**：global 与 targeted coverage 报告、阈值命令、covered module 列表。

### 4. Panel

- `npm ci`、`npm test` 和 `npm run build` 全部通过，且只使用 `panel/package-lock.json`。
- Vitest baseline 至少为 **63 test files / 192 tests**；减少 baseline 必须经过明确的
  change-control 说明，不能用删除测试换取通过。
- `npm run build:local && npm run check:artifact` 验证单文件 Panel artifact；五个 skin
  的核心登录、搜索、抓取、视频、Source、Network/WARP、Config 路由不得空白。

**Evidence**：npm/Vitest 机器输出、file/test count、build log、artifact checksum。

### 5. Docs

- `python3 tools/gen_docs.py --check` 同时验证 `docs/data-sources.md`、双 README、
  architecture registry 摘要和跨域 fetch 表。
- Markdown link checker 对 tracked Markdown 执行，internal anchors 与本地相对路径无 missing。
- `python3 scripts/ci/check_no_legacy_terms.py` 通过；公开命令、版本、source metrics 和 API
  字段与候选源码一致。

**Evidence**：gen-docs、link-check、legacy-term 三项日志及工具版本。

### 6. Clean install

- 从 candidate wheel 在五个彼此隔离、临时 HOME 的环境安装并 smoke：
  `edition-basic`、`edition-pro`、`edition-full`、`edition-full-crawl4ai`、
  `edition-full-scrapling`。
- 不允许 editable install、本机 site-packages、用户配置或预装 browser cache 帮助通过。
- Crawl4AI 与 Scrapling 变体分别安装，不把互斥依赖放进同一环境。

**Evidence**：wheel checksum、5 个 `pip freeze`、安装日志、HOME/venv isolation assertion。

### 7. MCP 与 edition 物理边界

- `edition-basic` 能导入 MCP surface，并且 registry 派生的 3 个 basic fetch provider
  （`builtin`、`mcp`、`site_crawler`）通过对应的 fixture/runtime smoke。
- Basic 环境中 FastAPI 未安装；LLM 与 full-only provider/plugin 必须返回明确 edition gate，
  不能因宿主环境泄漏而可用，也不能以裸 `ImportError` 崩溃。
- Pro/full 的 MCP stdio、tool listing、schema、multi-provider fetch 和 loopback transport
  与当前 edition 声明一致。

**Evidence**：`doctor edition --json`、module presence/absence probes、MCP tool schema 与调用报告。

### 8. Package contract

- Wheel 与 sdist 均从同一 `candidate_sha` 构建；版本、license、README、package data、
  generated Panel、entry points、optional extras 和 Python `>=3.10` metadata 正确。
- Wheel 不包含已删除 legacy modules，也不依赖源码 checkout 才能 import。
- SuperWeb2PDF 保持 PEP 508 fixed-commit direct reference；Hatch
  `allow-direct-references = true`、`web2pdf` extra、Docker `WEB2PDF_PACKAGE` 与 CI 安装源
  指向同一 archive。安装后必须验证 entry point、fetch handler 和 Playwright/PDF runtime。

**Evidence**：wheel/sdist file list、METADATA、import-surface report、archive ref、artifact checksums。

### 9. Functional fixtures

- Scrapling、Crawl4AI、article extraction 和 SuperWeb2PDF 的本地 fixture gate 全部 required PASS。
- Browser/runtime 必须真实启动；fixture 内容、输出格式和 report schema 必须通过验证。
- 缺 package、browser、handler 或 PDF 输出不能在 RC gate 中记为 SKIP/WARN。

**Evidence**：四项 JSON report、对应 Markdown diagnostic、runtime/package version。

### 10. Live zero-key

- Google Patents search、Wayback Availability 与 Wayback CDX 在 release 模式 required PASS；
  已定义的 CDX fallback 只有在报告保留原始 Availability 结果时才有效。
- 其他高波动 zero-key 源按 report 中预先声明的 required/WARN 分类判定；不得事后为了放行
  修改分类。
- Live 调用必须记录时间、出口环境、source、elapsed、状态和标准化错误，但不记录敏感值。

**Evidence**：zero-key JSON/Markdown report、required/WARN policy、run URL。

### 11. Containers

- Root、Hugging Face Space 和 ModelScope 三个 Dockerfile 都必须从 candidate source 构建、
  启动并通过 `/health`、`/readiness`、`/panel`、`/openapi.json`。
- Root 必须传 `SOUWEN_SOURCE_SHA=<candidate_sha>`；HFS/ModelScope 必须传
  `SOUWEN_REF=<candidate_sha>`。HFS/ModelScope 的默认全零模板、短 SHA 或分支名必须
  fail closed，不能回退到移动的 `main`。
- 未配置 admin password 且未显式 local test override 时，admin API 必须 locked。
- 镜像 label/build metadata 与 runtime readback 必须能证明 source SHA 为 `candidate_sha`；
  只看到 container running 或版本号相同不够。
- Base image digest、`scripts/warp-checksums.txt` 和 SuperWeb2PDF URL `#sha256=` 必须保持
  启用；任何下载校验缺失或绕过都为 FAIL。
- Root/HFS 的 WARP data/runtime-bin 必须回读 `/app/data` 与 `/app/data/bin`；ModelScope
  必须回读 `/home/user/app/data` 与 `/home/user/app/data/bin`，并证明 entrypoint `PATH` 与
  Python `WarpManager` 使用同一组环境变量。

**Evidence**：3 个 image digest、build log、source SHA、endpoint smoke JSON、admin-lock assertion。

### 12. Binary matrix

- PyInstaller 和 Nuitka 各构建 3 editions × 4 targets：Linux amd64、Linux arm64、
  macOS arm64、Windows amd64；每个 builder 12 个，共 **24 个 binaries**。
- 24 个 binary 全部验证 help、version、sources、config 和 doctor。
- Basic 追加 MCP smoke；pro/full 追加 loopback server smoke；full 追加 article extraction、
  PDF 与预装 plugin smoke。目标平台必须执行产物，不能只完成 cross-build。

**Evidence**：24 项 matrix report、目标 runner、binary checksum、每项 smoke 输出。

### 13. Security

- Candidate 环境的 Python 与 npm dependency scan 均无 unresolved Critical/High。
- 容器和 loopback server 的 admin 默认 locked；日志、reports、Panel artifact、source map、
  binary strings 抽检和 Git history scan 无真实 secret。
- SSRF、auth、redaction、plugin allowlist 和 public admin-open required tests 全部通过。

**Evidence**：pip/npm audit、secret scan、security test report、exception/waiver 清单。任何 waiver
必须由用户明确接受，并进入 manifest，不能只存在于聊天中。

### 14. Remote CI

- `CI`、`V2 CI`、`External Smoke Gate`、两个 binary workflow 和 container/deploy local gate
  在 `candidate_sha` 上全部 green。
- 每个 run 必须回读 head SHA、conclusion、required jobs 和 artifact inventory；分支名相同、
  rerun 成功或 merge 后别的 SHA green 都不能替代候选证据。

**Evidence**：workflow name、run URL、run ID、head SHA、conclusion、required job map、artifact names。

### 15. HFS promotion

- 只有用户明确批准后才能执行远端 promotion；批准前只允许本地/PR gate 和只读检查。
- Promotion 前要求目标 Space 已为 private，并分离三个 secret：`HF_TOKEN` 写管理面、
  `HF_SPACE_READ_TOKEN` 通过 private edge、`SOUWEN_SMOKE_BEARER_TOKEN` 作为 SouWen admin
  password。远端必须 `admin_open=false`；只通过 edge、不提供应用 token 时不得获得 admin。
- Promotion 前记录可信 rollback point：旧 Space repo SHA 等于旧 runtime SHA，旧 Dockerfile
  唯一 pin 40 位 `prior_souwen_ref`，并记录 `prior_runtime_stage`；只接受 `RUNNING` / `SLEEPING`
  稳定状态，不通过 preflight restart 改变 prior runtime。不存在 immutable rollback point 时必须
  在 mutation 前停止。
- Promotion 后的三段 provenance 分别是：Space repo SHA（wrapper commit）、
  `runtime.raw.sha`（必须等于 wrapper commit）、health/readiness `source_sha`（必须等于
  `candidate_sha`）。Wrapper SHA 通常不等于 SouWen source SHA。
- Surface/capability smoke 必须从 trusted `verifier_sha` 执行，不能把 app admin token 暴露给
  candidate checkout。失败时以 forward commit 恢复 prior wrapper 内容并验证旧 source；恢复
  或 readback 无法证明时 pause Space，原 promotion 仍为 FAIL。

**Evidence**：批准记录引用、prior/promoted/rollback Space SHA、source SHA、factory rebuild run、
surface/capability report、双层 auth/admin-open assertion。`RUNNING` 单独不构成 PASS。

### 16. RC assets

- RC 资产必须包含 wheel、sdist、24 个 binaries、`SHA256SUMS`、Python SBOM、Panel/npm SBOM、
  provenance/attestation 和 `release-manifest.json`。
- `artifacts[]` 只索引 payload assets；`release-manifest.json` 与 `SHA256SUMS` 属于
  `bundle_envelope`，避免 manifest 自哈希递归。`SHA256SUMS` 精确覆盖全部 payload 加 manifest，
  但不覆盖自身；最终目录必须等于 payload 与两个 envelope 文件的集合。
- 每个 payload 都有非空 size、SHA-256、producer run URL、candidate SHA 和适用的
  provenance/SBOM 关联。GitHub native attestation 是外部证明，不冒充 bundle 内普通文件。
  缺文件、多文件、重名覆盖、inventory 或 checksum 不一致均为 FAIL。
- 发布说明必须明确这是 RC、已验证层、未验证/高波动边界和 SuperWeb2PDF direct-reference
  安装边界；不得把 fixture、static doctor 或 `stability=stable` 写成 live provider 承诺。

**Evidence**：release asset API readback、manifest inventory diff、checksum verification、
attestation verification。

## `deployment-manifest.json` 最小字段

Deployment manifest 只索引轻量 HFS 验收证据，不得被 GitHub Release 消费：

```json
{
  "schema_version": 1,
  "evidence_profile": "deployment",
  "publishable": false,
  "version": "2.0.0rc1",
  "candidate_sha": "<40-hex>",
  "candidate_ref": "sha:<40-hex>",
  "verifier_sha": "<trusted-control-plane-40-hex>",
  "created_at": "<RFC3339 UTC>",
  "run_url": "<https URL>",
  "binary_count": 0,
  "gates": [],
  "remote_runs": [],
  "artifacts": [],
  "evidence_files": [],
  "containers": [],
  "hfs": {
    "promoted": true,
    "repo_sha": "<Space wrapper 40-hex>",
    "runtime_sha": "<same Space wrapper 40-hex>",
    "source_sha": "<candidate 40-hex>",
    "promotion_changed": true,
    "prior_repo_sha": "<40-hex>",
    "prior_runtime_sha": "<40-hex>",
    "prior_source_sha": "<40-hex>",
    "prior_runtime_stage": "RUNNING|SLEEPING",
    "surface_report": "hf-space-cd-surface-report.json",
    "capability_report": "hf-space-cd-capability-report.json"
  },
  "exceptions": []
}
```

最终 `deployment-evidence-*` artifact 只能包含 `deployment-manifest.json`、
`deployment-evidence.tar.gz` 与 `SHA256SUMS`；archive 可封装 common gate、package/SBOM、
container 与 HFS reports，但不得包含外层 PyInstaller/Nuitka release binary 或 binary-smoke
artifact。三个 envelope 文件必须由 native build provenance attestation 覆盖。

## `release-manifest.json` 最小字段

Manifest 是候选证据索引，不承载 secret。schema 至少固定以下字段；流水线可以向后兼容地
增加字段，但不能删除或改变已有字段语义：

```json
{
  "schema_version": 1,
  "version": "2.0.0rc1",
  "candidate_sha": "<40-hex>",
  "candidate_ref": "<ref>",
  "verifier_sha": "<trusted-control-plane-40-hex>",
  "created_at": "<RFC3339 UTC>",
  "bundle_envelope": {
    "manifest": "release-manifest.json",
    "checksums": "SHA256SUMS",
    "checksums_cover": "all release assets except SHA256SUMS itself",
    "artifacts_scope": "payload assets only"
  },
  "gates": [
    {
      "id": "python",
      "status": "PASS",
      "required": true,
      "run_urls": ["<https URL>"],
      "evidence": ["<artifact or report name>"],
      "notes": []
    }
  ],
  "remote_runs": [
    {
      "workflow": "<name>",
      "run_url": "<https URL>",
      "head_sha": "<trusted workflow 40-hex>",
      "candidate_sha": "<validated candidate 40-hex>",
      "conclusion": "success"
    }
  ],
  "artifacts": [
    {
      "name": "<exact filename>",
      "kind": "wheel|sdist|binary|sbom|report",
      "size": 1,
      "sha256": "<64-hex>",
      "producer_run_url": "<https URL>",
      "sbom": "<artifact name or null>",
      "provenance": "<artifact name or null>"
    }
  ],
  "containers": [
    {
      "surface": "root|hfs|modelscope",
      "image_digest": "sha256:<digest>",
      "source_sha": "<40-hex>",
      "report": "<artifact name>"
    }
  ],
  "hfs": {
    "promoted": false,
    "approval_reference": null,
    "environment": null,
    "environment_run_url": null,
    "repo_sha": null,
    "runtime_sha": null,
    "source_sha": null,
    "promotion_changed": null,
    "prior_repo_sha": null,
    "prior_runtime_sha": null,
    "prior_source_sha": null,
    "prior_runtime_stage": null,
    "surface_report": null,
    "capability_report": null
  },
  "exceptions": []
}
```

`status` 只允许 `PASS` / `FAIL` / `WARN` / `NOT_RUN`。Always-required gate 只有 `PASS` 才能
进入 RC-ready；HFS 仅在 `deploy_hfs=false` 时允许 `required=false, NOT_RUN`。`exceptions` 为空是
默认条件；非空 exception 必须包含 owner、reason、scope、expiry 和用户明确批准引用。
`environment_run_url` 只证明 job 绑定了 environment，不证明该 environment 实际配置了 required
reviewer；无法从 workflow 机器验证的批准不得伪造到 `approval_reference`，publish-ready 前必须由
维护者回读 GitHub environment/ruleset 后补充外部审核记录。

## Go / No-Go

- **Deployment-validated Go**：`deployment` profile 的 common gates 与 HFS promotion 全部
  `PASS`，两个外层 binary matrix 为预期 `skipped`，manifest 明确
  `publishable=false, binary_count=0`，Space repo/runtime/source 三段回读一致。该结论不得提升为
  RC-ready 或 publish-ready。
- **RC-ready Go**：15 个 always-required gate 全部 `PASS`，HFS 明确为未请求的 conditional
  `NOT_RUN`，且 `evidence_profile=release` 的 manifest/candidate/verifier SHA、
  payload/envelope inventory 与 checksum 一致。
- **Publish-ready Go**：RC-ready 条件成立，HFS promotion 另为 `PASS`，且发布前远端
  ruleset、`hf`/`release` environment approval 与 secrets 已人工回读。
- 任一 required `FAIL` / `WARN` / `NOT_RUN`、证据 SHA 漂移、manifest 缺失、未批准远端写、
  rollback point 缺失或未接受 security exception 都是 **No-Go**。HFS conditional
  `NOT_RUN` 只允许停在 RC-ready，不能发布。
