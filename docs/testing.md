# 测试策略

SouWen 的测试体系分成两层：

- **本地确定性测试**：默认 `pytest`，用于验证代码契约、配置、registry、parser、mock integration 和接口结构。
- **云端真实能力测试**：独立 `scripts/*_functional_check.py` 或 `scripts/*_smoke.py`，用于验证真实包、浏览器运行时、外部服务和部署环境。

这个分层的目标是让本地开发反馈保持稳定，同时让 CI 能发现 mock 测试覆盖不到的真实运行问题。

## GitHub Actions 五层语义

GitHub Actions 中的 job 应尽量回答单一问题，避免把单元测试、真实外部能力、
部署可用性和完整系统流程混在同一个日志里。当前测试体系按五层归因：

| 层级 | 目标 | 典型入口 |
|---|---|---|
| 单元测试 | 验证函数、模型、parser、配置合并等局部契约 | `pytest tests/` |
| 集成测试 | 验证 server、registry、handler 等模块组合 | `server-test` |
| 功能测试 | 验证真实 runtime / package 安装后的可用性 | `*_functional_check.py` |
| 冒烟测试 | 验证 target API、Docker/HF Space 入口仍活着 | `scripts/ci/run_profile.py`、`hf_space_smoke.py` |
| 系统测试 | 验证完整用户路径和多 profile 环境组合 | manual / nightly / release gate |

## 环境 Profile Runner

`scripts/ci/run_profile.py` 承接稳定、可重复的环境完整度 profile。它不安装依赖、
不下载 browser runtime，也不访问真实外部服务；workflow 仍负责显式安装环境，
runner 只负责运行场景并输出 JSON/Markdown report。

当前 profile：

| Profile | 覆盖内容 | 运行位置 |
|---|---|---|
| `server-contract` | target Server 的路由、认证、OpenAPI/API-major、HFS local surface 与 Panel runtime 前置契约 | V2 CI、HF Space CD local preflight |
| `sdk-contract` | target-only OpenAPI 与 generated Python sync/async SDK 的可重复生成、semantic/API-major、auth/error/clean import 合同 | V2 CI、HF Space CD local preflight |
| `provider-runtime` | 内部 optional provider 的 importability、feature matrix 与互斥 browser runtime | CI / provider-runtime gate |

`server-contract` 与 `sdk-contract` 是 A3c 的产品 contract 名称；
`provider-runtime` 仅是内部实现验证，不能替代 package/SDK 证据。三者都通过明确的
leaf extras 安装所需实现；它们不是新的产品 tier 或 package matrix。

示例：

```bash
python scripts/ci/run_profile.py \
  --profile server-contract \
  --profile sdk-contract \
  --json-report artifacts/target-contract-profile.json \
  --markdown-report artifacts/target-contract-profile.md
```

OpenAPI artifact 可单独验证：

```bash
PYTHONPATH=src python3 tools/gen_openapi.py --check
```

## 本地确定性测试

默认本地测试不应依赖真实互联网、浏览器运行时、真实 API key 或云端服务。

适合留在 `pytest` 的内容：

- schema / model validation。
- config merge、环境变量解析和凭据字段解析。
- registry / source catalog 一致性。
- provider 注册、handler 注册和参数传递。
- parser 对固定响应的处理。
- HTTP error mapping、timeout、retry、rate limit 行为。
- 使用 `pytest-httpx`、monkeypatch 或本地 fixture 的 mock integration。
- FastAPI route 参数校验和响应结构。
- local catalog 的 SQLite schema / FTS、完整性、idempotent import、失败 checkpoint、配置解析和
  显式 source 的 unavailable 映射；fixture 只能使用仓库内 RDF/XML 样本，不能下载 catalog
  archive 或 ebook。

推荐本地命令：

```bash
pip install -e ".[dev,server,tls,web,robots,scraper]"
PYTHONPATH=src python3 -m pytest -q
python3 -m ruff check src/ tests/ scripts/
python3 -m ruff format --check src/ tests/ scripts/
```

## 云端真实能力测试

真实外部能力应放在专项脚本中，并由 GitHub Actions 专项 job 执行。

适合专项脚本的内容：

- Playwright / Patchright / Crawl4AI / Scrapling 等 browser runtime。
- 真实第三方 Python 包安装、import 和最小调用。
- 真实外部网站抓取或动态渲染抓取。
- Hugging Face Space live endpoint / post-deploy smoke。
- 需要 API key、代理、WARP、自建 URL 的 provider。

专项脚本必须独立运行，不依赖 pytest fixture。运行时安装行为应在 workflow step 中显式呈现，不应隐藏在 Python 脚本里。

Project Gutenberg local-catalog 的 bounded live evidence 使用
`scripts/local_catalog_functional_check.py --mode live --execute --required`：只获取一条官方
RDF/XML sample（`pg11.rdf`），写入临时数据库后验证重复导入、FTS、detail 与 integrity。
它不会下载 canonical archive、不会访问 RDF 声明的 format/resource URL，也不会下载 ebook。
canonical archive 的完整导入仍由维护者在明确批准的环境中执行；普通 pytest、PR build 与
HF Space smoke 不携带个人 local catalog 数据库。

台湾新书资讯的 bounded evidence 使用
`scripts/taiwan_new_books_functional_check.py --mode live --execute --required`：它只下载 data.gov.tw
当前声明的一份 NCL UTF-8 CSV 到临时目录，验证重复导入、SQLite integrity 与 FTS5；不访问书目之外的
图书、预览或全文 URL，也不把新书 metadata 解释为访问或再分发授权。

## Outcome 语义

所有专项脚本使用统一 Outcome。

| Outcome | 语义 | 退出码影响 |
|---|---|---|
| `PASS` | required check 全部通过 | 0 |
| `WARN` | 非 required check 失败或退化 | 0 |
| `FAIL` | required check 失败，核心契约破裂 | 1 |
| `SKIP` | 缺少 secret、runtime 或显式跳过 | 0 |

`FAIL` 示例：

- import 失败。
- provider 注册失败。
- required 字段缺失或解析失败。
- SSRF guard / URL allowlist / credential guard 没生效。
- required endpoint 返回非预期结构。
- browser runtime 已安装但启动失败。

`WARN` 示例：

- 非关键外部源单次网络波动。
- 可选字段缺失。
- 性能退化但未超过硬超时。
- 外部服务短暂 429，但核心 fixture 和 required check 正常。

`SKIP` 示例：

- 缺少 required secret。
- 显式 `--mode offline`。
- fork PR 不允许访问 Environment secret。
- runtime 未安装，且当前 job 不负责安装。

## Report 规则

专项脚本必须支持 JSON report 和 Markdown report：

```bash
python scripts/<name>_functional_check.py \
  --mode fixture \
  --timeout 30 \
  --json-report artifacts/<name>.json \
  --markdown-report artifacts/<name>.md
```

JSON report 是 source of truth，Markdown 只作为人类可读渲染。CI 应上传 report artifact，方便排障和后续趋势分析。

## CI 分级

| 层级 | 运行时机 | 适用内容 |
|---|---|---|
| PR required | pull request | 稳定、低成本、关键外部能力 smoke |
| Nightly / manual | schedule / workflow_dispatch | 高波动真实外部源、secret-backed provider |
| Release gate | tag / release branch / manual | 发版前完整重型外部能力集合 |

PR required 只覆盖关键最小 smoke。高波动外部源不应默认阻断每个 PR，但 nightly/manual 失败必须能被追踪，不能静默遗忘。

## 二进制构建 Profile

RC2 目标发布面由 `Build PyInstaller Server bundles` 构建，固定使用四个平台的
target-native runner：

| Platform | Runner architecture | Release archive |
|---|---|---|
| Linux amd64 | `x86_64` | `souwen-server-2.0.0rc2-linux-amd64.tar.gz` |
| Linux arm64 | `aarch64` / `arm64` | `souwen-server-2.0.0rc2-linux-arm64.tar.gz` |
| macOS arm64 | `arm64` | `souwen-server-2.0.0rc2-macos-arm64.tar.gz` |
| Windows amd64 | `AMD64` / `x86_64` | `souwen-server-2.0.0rc2-windows-amd64.zip` |

每个 archive 是 PyInstaller `onedir` Server bundle，包含 `souwen-server` executable、
`runtime.source.sha`、Playwright Chromium runtime 和构建后的 Panel artifact。Runner 必须先
生成最终 archive，再解压到新目录执行 `.github/actions/server-bundle-smoke`；直接运行 `dist/`
目录不构成发布证据。Smoke 必须覆盖 health/readiness、version/source/API-major、target rollout、
Browser Worker、Admin fail-closed、Provider API、OpenAPI checksum 和 Supervisor 干净退出。

当前唯一 binary release evidence 是 `Build PyInstaller Server bundles` 的四平台
target-native archive。旧 CLI/PyInstaller/Nuitka workflow 不构成 current evidence，
也不能把任何 CLI binary 重新命名为 Server bundle。

`server-contract` 与 `sdk-contract` 表达产品 contract；`sdk-contract` 包含 frozen target-only
OpenAPI 的可重复生成门禁；`provider-runtime` 表达内部可选
provider runtime。各 profile 使用明确 leaf extras 安装所需实现依赖，且不形成新的
对外 tier 或 package matrix。

## V2 / main 发布前 Gate

v2 release candidate 已合回 `main`。`V2 CI` 继续作为 v2 public surface 的
专用 gate，并在 `main` 与需要保留的 v2 集成分支上运行；生产 CD、二进制构建
和外部 release gate 仍保持独立触发。

自 2026-07-26 起 `CI` 与 `V2 CI` 按 lane 分档运行（业主批准的 CI 瘦身）：

- fast lane（普通 PR 与 `main` push）：`CI` 只跑 architecture、lint、docs-check、
  单组合 pytest（Python 3.13 + ubuntu-24.04）与 panel-build；`V2 CI` 只跑
  bootstrap 与 Provider v2 conformance。每个 PR 的检查数从 53 项收敛到约 12 项。
- full lane（release 复用调用、手动 `workflow_dispatch`、`v*` tag push）：运行
  下方完整矩阵与全部 gate。release evidence 与 tag 验收不受 fast lane 影响。

完整 lane 下当前 `V2 CI` 必须覆盖：

- bootstrap gate：registry/docs 测试、`tools/gen_docs.py --check`、import surface
  单测、wheel surface 检查和 registry baseline 输出。
- full pytest matrix：安装 `.[dev,server,tls,web,robots,scraper]`，覆盖 Ubuntu Python
  3.10/3.11/3.12/3.13，以及 macOS/Windows Python 3.11；避免把缺少 Server
  或 scraper runtime 误报成产品行为回归。
- Provider v2 conformance：先以 `tools/provider_migration_inventory.py --check --require-complete`
  和 `tools/gen_provider_spec_drafts.py --check` 校验 110 源 inventory、104 个待审草稿与生成物；
  再运行 SPI、typed spec/factory/resolver、manifest registry、Provider Manager、自动发现的
  OpenAlex/ERIC/PatentsView 九项 Search matrix，以及 builtin Fetch、UniAPI 和 provider-specific
  deterministic tests。整个 gate 不访问网络、browser runtime、HOME 或真实 secret，并由
  V2 readiness summary fail closed 汇总。
- server contract：安装 API 测试依赖后运行 `server-contract`，上传 target Server
  JSON/Markdown evidence。它覆盖 local API surface，不证明外部源在线。
- SDK contract：验证 target OpenAPI、generated Python bindings freshness、sync/async operation、
  API-major preflight、auth/error/request-ID、无自动 retry 与 clean import；TypeScript SDK 仍由 C2c 交付。
- provider runtime：使用明确 provider extras 覆盖核心 source、doctor 与
  fetch handler import surface，并校验 optional provider declaration；`crawl4ai` /
  `scrapling` 的互斥 browser runtime 仍由专项 functional gate 覆盖。
- panel build：`npm ci`、TypeScript check、Vitest、`npm run build:local` 和
  `src/souwen/server/panel.html` 产物验证。

这些 gate 是 main 上 v2 candidate 发布前的必过项。它们不负责生产部署或二进制
release 产物上传。

`External Smoke Gate` 是外部能力的 PR-required / nightly / release gate 入口：

- `workflow_dispatch`：手动选择 `suite=pr-required` 或 `suite=release`。
- `suite=pr-required`：跑真实包 import 与本地 fixture 契约，不触发 Scrapling
  live browser 抓取；Crawl4AI 浏览器 runtime 缺失按非阻断 SKIP/WARN 语义收口。
- `suite=release`：跑发布候选 gate；Scrapling 使用 live + dynamic browser，
  Crawl4AI 要求 browser runtime 可用，required `FAIL` 视为发布阻断。
- `schedule`：每天 02:17 Asia/Shanghai 跑 nightly；其中 zero-key live source
  gate 会真实探测 Google Patents / Wayback，失败时创建或更新带 `ci:external` /
  `smoke-failure` label 的 issue，恢复后自动关闭。
- tag `v*`：作为 release gate 跑 Scrapling / Crawl4AI 真实运行时 gate，并把
  zero-key live source 失败视为发布阻断。
- 每个 gate job 上传 JSON + Markdown artifact，JSON 仍是 source of truth。

v2 发布前，`External Smoke Gate` 不要求每个普通 PR 自动运行；它应在候选
版本 head、release branch 或最终 tag 前手动以 `suite=release` 跑一次，并把
required `FAIL` 视为发布阻断。

## 当前专项矩阵

| 能力 | 层级 | pytest 保留内容 | 专项脚本覆盖 | CI job |
|---|---|---|---|---|
| Scrapling | PR required / release | provider 注册、配置解析、fixture/mock 契约 | PR-required 覆盖真实 `scrapling.fetchers` import + 本地 fixture；release 追加 live dynamic browser 抓取 | `Scrapling 云端功能测试` |
| Crawl4AI | PR required / release | handler 注册、参数派发、错误聚合契约 | 真实 `crawl4ai.AsyncWebCrawler` import、本地 fixture browser 抓取；release 要求 runtime 缺失直接 FAIL | `Crawl4AI 云端功能测试` |
| Article extraction | PR required / release | `newspaper` / `readability` handler 注册、参数派发和错误聚合契约 | 真实 `newspaper4k` / `readability-lxml` import + 本地 HTML fixture；release 可用 `--require-runtime` 将缺 runtime 视为 FAIL | `Article extraction 云端功能测试` |
| Zero-key live sources | Nightly / release | Google Patents / Wayback parser、SSRF guard、registry 契约和 mock HTTP 单测 | `scripts/zero_key_functional_check.py --mode live` 对 Google Patents search、Wayback Availability 与 CDX 做真实免 Key 探测；当 Availability API 无 closest 但同 URL 的 CDX 200 快照可证明可用时，availability check 记录 `cdx_fallback` 通过；默认 live 失败为 WARN，release 可加 `--required` | `Zero-key live source gate` |
| OpenAlex anonymous contract | Manual | OpenAlex 请求参数、anonymous/key 行为和 registry metadata | `scripts/openalex_functional_check.py --mode live --execute --required` 只发送一次匿名 search，主动清除本地配置 key；写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| UniAPI Ark model-bound search | Manual / paid authorization | selected Ark concrete source 的 immutable scheme/model、single-attempt Responses receipt、structured annotations 与受限 fetch evidence | `scripts/uniapi_search_functional_check.py --source <concrete-source> --mode dry-run` 不读凭据、不发网络；仅在已获计费授权后使用 `--mode live --execute --required`。每次只运行一个显式 source，不重试、不自动换 model；报告会保留 source/scheme/model、工具类型、annotation/usage/fetch 计数并删除 key、private gateway base URL、request/response ID、raw/encrypted content | Maintainer manual evidence |
| ERIC anonymous search | Manual | ERIC pagination、normalizer 与 registry metadata | `scripts/eric_functional_check.py --mode live --execute --required` 只发送一次官方匿名 metadata search，写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| OSTI.GOV anonymous search/detail | Manual | OSTI `q` 参数、分页、search/detail normalizer 与 registry capability metadata | `scripts/osti_functional_check.py --mode live --execute --required` 发送一次官方匿名 search 和同一记录的一次 detail 请求；写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| DataCite anonymous research-output search/detail | Manual | DataCite JSON:API pagination、dataset/software/text/event fixture normalizer、resource type、rights、related identifiers、funding 与 content URL metadata | `scripts/datacite_functional_check.py --mode live --execute --required` 只发送一次匿名 DOI metadata search，随后对同一 DOI 请求一次 detail；保留 resource type、rights 和声明 links，不跟随 landing URL、不下载内容，也不把 metadata 解释为下载或再分发授权 | Maintainer manual evidence |
| Figshare anonymous article search/detail | Manual | Figshare public API v2 POST search 的 `page` / `page_size` 请求体、dataset/software/figure fixture normalizer、license、multiple files、`is_link_only` 和 declared download URL metadata | `scripts/figshare_functional_check.py --mode live --execute --required` 只发送一次公开 article search，随后对同一 article 请求一次 detail；保留 article type、license、files 与 declared URLs，不跟随或下载文件，也不把 source metadata 解释为访问或再分发授权 | Maintainer manual evidence |
| Project Gutenberg local RDF catalog | Manual | SQLite schema/FTS、官方 RDF/XML parser、metadata/resource-link mapping、idempotent import、显式 unavailable 与 CLI/REST error mapping | `scripts/local_catalog_functional_check.py --mode live --execute --required` 只获取官方 `pg11.rdf`，导入临时 SQLite 后验证 repeat import、FTS、detail 和 integrity；不下载 RDF archive 或 ebook，也不跟随 declared format URL；报告 source、sample ID、observed SHA/size、rights 和 resource count | Maintainer manual evidence |
| Taiwan new-books local CSV catalog | Manual | data.gov.tw dataset 6730 / NCL UTF-8 CSV parser、ISBN identity、metadata-only mapping、idempotent import 与 explicit unavailable | `scripts/taiwan_new_books_functional_check.py --mode live --execute --required` 只下载一份 data.gov 声明的 NCL CSV，导入临时 SQLite 后验证 repeat import、integrity 和 FTS5；不下载图书内容或跟随非 catalog URL | Maintainer manual evidence |
| Open Library anonymous work search/detail | Manual | Open Library search 参数、work/edition normalizer 与 registry metadata | `scripts/open_library_functional_check.py --mode live --execute --required` 只发送一次匿名 work search，随后对同一 work 请求一次有界 edition detail；只验证公开书目/资源元数据，不推断借阅、阅读或下载权利；写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| Internet Archive anonymous catalog search/detail | Manual | Internet Archive Advanced Search/Metadata API 参数、texts 馆藏 normalizer、resource access 与 registry metadata | `scripts/internet_archive_functional_check.py --mode live --execute --required` 只发送一次匿名 catalog metadata search，随后对同一 identifier 请求一次有界 metadata detail；只验证馆藏和 resource metadata，绝不借阅、阅读或下载文件；license/access 按单条上游记录保守报告；写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| Library of Congress anonymous catalog search/detail | Manual | LOC `fo=json` pagination、item envelope、resource/access normalizer 与 registry metadata | `scripts/library_of_congress_functional_check.py --mode live --execute --required` 只发送一次官方 catalog search 和同一 record 的一次 item detail；只验证 record/resources metadata，不下载数字资源；rights/access 按单条记录保守报告 | Maintainer manual evidence |
| DOAB anonymous OAI-PMH catalog/detail | Manual | DOAB OAI-PMH `oai_dc` / `mets`、Books set 有界 harvest filter、identifier/license/bitstream normalizer 与 experimental registry contract | `scripts/doab_functional_check.py --mode live --execute --required` 只发送一次 Books set metadata harvest，随后对同一 record 请求 `oai_dc` 和 `mets`；只验证书目、license、publisher 与声明 bitstream links，不下载文件；DOAB metadata dissemination 与逐本正文 license 分开报告 | Maintainer manual evidence |
| OAPEN anonymous OAI-PMH catalog/detail | Manual | OAPEN OAI-PMH `oai_dc` / `mets`、独立 Books set 有界 harvest filter、funding/license/bitstream normalizer 与 experimental registry contract | `scripts/oapen_functional_check.py --mode live --execute --required` 只发送一次 OAPEN Books set metadata harvest，随后对同一 OAPEN record 请求 `oai_dc` 和 `mets`；只验证书目、funding、license、publisher 与声明 bitstream links，不下载文件，且不与 DOAB source ID/rights 混用 | Maintainer manual evidence |
| LibriVox anonymous audiobook catalog/detail | Manual | LibriVox title/author search、numeric audiobook ID、extended section/reader/audio-link normalizer、RSS/IA/archive resource metadata 与 registry explicit-only contract | `scripts/librivox_functional_check.py --mode live --execute --required` 只发送一次官方 title（或 `--search-field author`）search，随后对同一 audiobook ID 请求一次有界 extended metadata；只验证书目、reader 与声明 audio/RSS/外部链接，绝不请求、下载或转码媒体；`copyright_year` 与 rights/public-domain 按上游记录和适用法域保守报告；写入 JSON/Markdown evidence，不进入普通 pytest 或自动 PR gate | Maintainer manual evidence |
| Wikisource language-bound catalog/detail | Manual | `zh` / `en` allowlist、默认 `zh`、MediaWiki search/detail/revision fixture、redirect、大小限制与 rights/provenance 分层 | HF Space smoke 仅以 `sources=wikisource` 和中文 `論語` 做一次 catalog metadata search；不读取 page/revision/subpage。页面 detail 通过 `get_wikisource_page_detail()` 的明确 language/title 请求，并将 `content_format`、size、provenance、站点贡献许可与底本 rights 分开验证；不导入 dumps 或递归遍历 | Maintainer manual evidence |
| HF Space smoke | deploy smoke / release gate | `hf_space_smoke` 参数、矩阵覆盖、admin-open gate 和 report 渲染的确定性单测 | private edge + 应用 admin 双层鉴权、surface/capability、admin-open required gate、统一 JSON Outcome report | `HF Space CD` |

## Secrets 边界

需要 API key、账号、代理或自建服务 URL 的专项测试必须挂 GitHub Environment。fork PR 默认不运行 secret-backed smoke。

默认权限：

```yaml
permissions:
  contents: read
```

只有自动创建 issue 或发布评论的 workflow 才增加写权限。
