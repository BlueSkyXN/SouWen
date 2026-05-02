# Changelog

## [Unreleased] — Source Catalog Governance（2026-05-02）

### Features
- **feat(registry)**：扩展 `SourceAdapter` / `SourceMeta`，新增 `auth_requirement`、`credential_fields`、`optional_credential_effect`、`risk_level`、`risk_reasons`、`distribution`、`package_extra`、`stability` 等 source catalog 元数据。
- **feat(doctor/server/cli)**：统一 doctor、`/sources`、admin source config、`souwen sources` 与 `souwen config source` 的鉴权/风险/分发展示口径，并支持多字段凭据。
- **feat(panel)**：更新 source 相关 API 类型，并在 souwen-google / souwen-nebula 数据源页展示风险与分发标签。

### Behavior
- 可选凭据源不再被粗略显示为"必须 Key"；缺少可选 Key 时按 `optional_credential_effect` 显示 `ok` 或 `limited`。
- doctor 与 admin doctor 汇总现在区分严格 `ok`、可用 `available`、降级 `degraded` 与失败 `failed`；`limited` / `warning` 仍计入可用源。
- `/api/v1/sources` 从运行时 live registry 派生，插件注册/注销后的数据源不会被静态兼容视图缓存误报。
- `unpaywall` 按实际客户端要求改为必须 `unpaywall_email`，继续保留在实验/排除旧 `ALL_SOURCES` 视图中。
- `tools/gen_docs.py` 默认只生成内置源清单，避免本机已安装外部插件造成文档漂移；可用 `--include-plugins` 查看运行时插件 catalog。

### Docs
- 更新 README、架构文档、新增数据源指南、插件对接规范、API 文档和自动生成的数据源清单。

### Tests
- 增加 registry catalog 元数据合法性、多字段凭据、source catalog 维度查询、server/API 返回字段等测试覆盖。

## [Unreleased] — 全面评审修复（2026-04-29）

### Bug Fixes
- **fix(panel)**：修正 Wayback Save 前端调用路径（`/api/v1/wayback/save` → `/api/v1/admin/wayback/save`）。原路径与后端 admin 路由前缀不一致，导致所有 5 个皮肤的 ToolsPage 中"存档"按钮固定 404。
- **fix(panel)**：补齐 `souwen-google` 皮肤 `PAGE_TITLE_KEYS` 缺失的 `/warp` 路径标题映射，避免落到默认 `nav.dashboard`。
- **fix(panel/skins)**：carbon / apple / ios 三个皮肤补齐 `/video` 与 `/tools` 导航入口，与 souwen-google / souwen-nebula 保持一致；之前路由已注册但侧栏不可达。
- **fix(panel/skins)**：更新 souwen-google / souwen-nebula 的 `MainLayout.tsx` 顶部注释，反映当前 9 个 NAV_ITEMS（dashboard / search / fetch / video / tools / sources / network / warp / config）。

### Refactor
- **refactor(server/routes)**：把 `/admin/wayback/save` 端点从 `routes/admin/warp.py` 拆出到独立的 `routes/admin/wayback.py`，保持 SRP；`admin_router` 在 `routes/admin/__init__.py` 中合并新模块。

### Docs
- **docs(README)**：更正 fetch 横切能力计数（15+4 → 16+4 = 20 源），与 `docs/data-sources.md` 自动生成结果对齐。
- **docs(api-reference)**：更新示例 JSON 中过期的 `version` 字段（0.6.3 → 1.1.1），并补充"动态返回，示例值仅作参考"的说明。
- **docs(api-reference)**：补齐 fetch provider 列表中遗漏的 `arxiv_fulltext`，并把"19 个提供者"修正为"20 个"，与 registry 实际注册一致。

## v1.1.2 — AI Workflow 安全加固与功能深化（2026-05-04）

### Features
- **ai-review.yml**: 新增空输出回退评论（Codex 无输出时自动发布诊断消息而非静默跳过）
- **ai-agent.yml**: 新增 `trigger_source` 输出字段（pr_comment / issue_comment / workflow_dispatch）
- **ai-agent.yml**: 新增触发来源能力分级（不同触发方式有不同 gh CLI 操作权限）
- **ai-agent.yml**: 新增 Job Summary 步骤（所有触发来源均可在 Actions Summary 中看到执行结果）
- **ai-agent.yml**: open-pr 更新时现在同步更新 title + base_ref（修复重复运行时 base 不同步问题）
- **ai-agent.yml**: 恢复 GH_TOKEN（使用 github.token）让 AI 可自主 `gh pr comment` / `gh issue comment`

### Security
- **ai-agent.yml**: 三重 OWNER 验证（YAML `if` + JS name check + API `admin` permission check）
- **ai-agent.yml**: `persist-credentials: false` + 单独凭据配置步骤（防止 git creds 泄露给 Codex workspace）
- **ai-agent.yml**: Direct mode 使用显式 `--force-with-lease=ref:sha` 防止覆盖并发推送
- **ai-agent.yml**: Prompt 安全红线：禁止打印/写入/发送 token 值
- **ai-review.yml**: 评审 Codex 不获取 GH_TOKEN（review 是只读操作）

### Observability
- 两个 workflow 均新增 Codex 前后诊断步骤（pre/post diagnostic）
- `RUST_LOG=info` 启用 Codex CLI 调试日志
- Codex timeout 统一 60 分钟

### Docs
- 两个 workflow 添加版本号 1.1.2 + 架构注释文档头
- 通知 Job 注释标明 ChatOps 评论 vs Job Summary 的适用场景
- ai-review.yml 底部评论从 `/ai-fix` 更新为 `/ai-do`（对齐新 ai-agent 命令）

## v1.1.1 — WARP 动态组件管理与非阻塞启动（2026-04-28）

### Features
- **新增 WarpInstaller 运行时安装器**：从 GitHub Releases 下载 usque/wireproxy/wgcf 到 `/app/data/bin/`，支持 `GH_PROXY` 代理
- **新增 5 个动态管理 API 端点**：`/admin/warp/components`、`/admin/warp/components/install`、`/admin/warp/components/uninstall`、`/admin/warp/switch`、`/admin/warp/events`（SSE 实时推送）
- **WarpManager 增强**：`_find_binary()` 搜索 runtime bin 目录，优先级：配置路径 > runtime bin > system PATH
- 新增 WARP 组件管理卡片：展示 usque / wireproxy / wgcf 安装来源与版本，并支持一键安装（5 个皮肤全覆盖）
- HFS/ModelScope Dockerfile 补装 usque v3.0.0 二进制

### Behavior
- **非阻塞启动**：entrypoint.sh 默认跳过同步 `warp-init.sh`（`WARP_ENTRYPOINT_INIT=0`），由 Python WarpManager 后台异步启动。设为 `1` 恢复旧行为

### Security
- WARP admin API 端点不再泄露内部异常信息，错误消息改为通用提示

### Docs
- CHANGELOG / README / warp-solutions.md / souwen.example.yaml 补充动态管理和非阻塞启动说明

## v1.1.0 — WARP 五模式扩展（2026-04-27）

### Features
- 新增 3 种 WARP 代理模式：usque MASQUE/QUIC、warp-cli 官方客户端、external 外部代理
- 新增前端 WarpPage 专属管理页面（souwen-nebula 皮肤）
- 新增 CLI `souwen warp` 命令组：status / enable / disable / modes / register / test
- 新增 API 端点：`/warp/modes`、`/warp/register`、`/warp/test`、`/warp/config`
- Dockerfile 预装 usque v3.0.0 二进制

### Behavior
- 自动模式降级链：external > kernel > usque > wireproxy
- NetworkPage WarpCard 简化为摘要卡片，引导至专属页面

### Docs
- 新增 WARP 方案对比文档：`docs/warp-solutions.md`

## [Unreleased] — Plugin System

### Architecture
- 新增插件系统：通过 setuptools entry_points 或配置文件发现外部数据源
- Fetch dispatch 重构：20 个 if/elif 分支 → handler 注册表模式
- 支持双模式加载：运行时发现 (`pip install superweb2pdf`) 和打包嵌入 (`pip install "souwen[web2pdf]"`)

### Features
- `src/souwen/plugin.py`：插件发现与加载模块
- `register_fetch_handler()`：外部 fetch provider 注册 API
- `_reg_external()`：外部适配器注册（重名自动跳过）
- `SOUWEN_PLUGINS` 环境变量 / `plugins` 配置字段支持手动指定插件
- `web2pdf` optional dependency：`pip install "souwen[web2pdf]"`

### Docs
- 新增 `docs/plugin-integration-spec.md`：插件对接规范
- 新增 `examples/minimal-plugin/`：最小示例插件
- 更新 `docs/architecture.md`、`docs/adding-a-source.md`

### Tests
- 新增 `tests/test_plugin.py`（37 tests）：插件系统全覆盖
- 新增 `tests/test_fetch_handlers.py`（9 tests）：handler 注册表测试
- 更新 `tests/registry/test_consistency.py`：外部插件一致性检查

### CI
- 新增 `plugin-test` job：安装 web2pdf extra，验证 entry_point 发现
- import-check 步骤扩展：插件模块导入验证

## v0.9.0 — v1 过渡版（2026-04-22）

**架构级改造**：建立数据源单一事实源（registry），引入 facade 门面层，按 v1 的 10 个 domain 重组目录。保持所有 v0 入口（Python import / CLI 命令 / REST 路径）完全兼容。

### Architecture
- **feat(registry)**：建立 `souwen.registry` 单一事实源。76+ 源的元数据 + 执行适配（`MethodSpec.param_map`）集中在 `registry/sources.py`。新增源的代价从"改 7 处"降到"改 1-2 处"。
- **feat(adapter)**：定义 `SourceAdapter` + `MethodSpec` 抽象，替代 v0 的 `SourceMeta` + `_PAPER_SOURCES/_PATENT_SOURCES` 24 个 lambda + `engine_map/source_map` 两张 45 条映射表。
- **feat(facade)**：新增 `souwen.facade` 门面层：`search(domain=, capability=)` / `fetch_content(urls, provider=)` / `archive_lookup/save/fetch` / `search_all(domains=)`（D1 显式跨域聚合）。
- **feat(core)**：抽取平台层 `souwen.core`（http_client / rate_limiter / retry / session_cache / fingerprint / exceptions / scraper / parsing / concurrency）。原路径保留 shim，外部 import 不破坏。
- **feat(domain)**：按 v1 新增 domain 子包：`social/` / `video/` / `knowledge/` / `developer/` / `cn_tech/` / `office/` / `archive/` / `fetch/providers/`，`web/` 新增 `engines/` / `api/` / `self_hosted/` 子目录（均以 re-export shim 的形式；客户端文件暂留原位）。

### Domain 变化
- **archive 独立 domain**（原 v0 放在 fetch）：`souwen archive cdx/check/save/fetch`，底层共享 `WaybackClient`。
- **cn_tech 独立 category**：csdn / juejin / linuxdo 从杂项归入 `ALL_SOURCES["cn_tech"]`（v0 漏列）。
- **DeepWiki 归 fetch**（D2）：代码验证 DeepWikiClient 只有 `fetch`，没有 search。

### Patent
- **refactor**：统一 Google Patents 实现——删除 `patent/google_patents.py` 的 Playwright 孤儿版 + 自写 _BrowserPool，`GooglePatentsClient` 成为 `GooglePatentsScraper` 的别名。`scraper` extras 移除 `playwright` 依赖。

### Concurrency
- **fix(concurrency)**：`loop._souwen_sem = sem  # type: ignore` 黑魔法 → `core.concurrency.get_semaphore(channel)` 基于 `WeakKeyDictionary[loop, Semaphore]`。两个独立 channel（`search` / `web`）互不阻塞；loop GC 后自动清理。

### Integrations
- **refactor(mcp)**：`integrations/mcp_server.py` → `integrations/mcp/server.py`；`integrations/_tools_bilibili.py` → `integrations/mcp/tools/bilibili.py`。原路径 shim 保留。

### Tests
- **test(registry)**：新增 `tests/registry/test_consistency.py` 含 21 项硬断言（D11 的 8 项 + 13 项补充）。每个 MethodSpec 的方法名在 Client 上真实存在 / 每个 param_map 的目标参数是方法签名参数 / 每个 config_field 在 SouWenConfig 上存在 / SourceType 规范化后 ⊆ registry / 12 项标准 capability 全部覆盖 / 各 domain 至少 1 个源等。

### Dependencies
- **chore(deps)**：删除 `requirements.txt` / `requirements-server.txt` / `requirements-full.txt` 三份文件。pyproject.toml `[project.optional-dependencies]` 是唯一事实源。Docker/HFS/ModelScope 改用 `pip install ".[server,tls,web,scraper]"`。
- **chore(deps)**：`scraper` extras 移除 `playwright`（v1 不再使用）。

### CI
- **ci**：新增 `.github/workflows/registry-consistency.yml`（每 PR 运行 registry 一致性测试）
- **ci**：新增 `.github/workflows/panel-sync.yml`（检查 panel/src/** 改动是否同步到 src/souwen/server/panel.html）

### Tools
- **tools**：新增 `tools/gen_sourcetype.py`（从 registry 派生 SourceType + `--check` 模式供 CI）
- **tools**：新增 `tools/gen_docs.py`（从 registry 生成 docs/data-sources.md 的 Markdown 表格）

### Frontend
- **feat(hooks)**：新增 `panel/src/core/hooks/useSearchPage.ts` 通用搜索 hook（按 domain 参数化）。4 皮肤 SearchPage 的视图层改造按后续版本推进。

### Docs
- **docs**：全量重写 README.md（按 v1 特性组织）
- **docs**：重写 docs/architecture.md（v1 三层分离 / SourceAdapter 核心 / 12 capability 矩阵 / 21 项一致性测试）
- **docs**：`tools/gen_docs.py -o docs/data-sources.md` 生成完整数据源清单（83 个源）

### Misc
- **chore**：`.gitignore` 中 CLAUDE.md 条目加注释说明（已入库文件不受影响）

### Breaking Changes

**无**。所有 v0 符号通过 shim 保留：
- `from souwen.paper import OpenAlexClient` ✓
- `from souwen.web import DuckDuckGoClient` ✓
- `from souwen.http_client import SouWenHttpClient` ✓
- `souwen search paper "..."` CLI 命令 ✓
- `GET /api/v1/search/paper?q=...` REST 路径 ✓
- `SouWenConfig.openalex_email` 等配置字段 ✓

v0 的 ALL_SOURCES 在 v1 从 registry 派生，**数值修正**：
- `ALL_SOURCES["general"]` 从 16 → 21（补全 ddg_news/images/videos + bing_cn + metaso）
- `ALL_SOURCES["social"]` 从 3 → 5（补全 twitter + facebook）
- `ALL_SOURCES["cn_tech"]` 新分类（v0 漏列，3 源）
- 总计 73 → 83

---

## v0.8.0

大版本升级：76 数据源 × 4 皮肤 × 全模式适配。

### Feature
- **VideoPage 全皮肤适配**：YouTube 热门/视频搜索/字幕提取页面从 souwen-classic 移植到 carbon/apple/ios（含 useVideoPage hook 抽取）
- **ToolsPage 全皮肤适配**：Wayback Machine CDX/可用性检测/存档工具页面移植到全部 4 套皮肤（含 useToolsPage hook 抽取）
- **版本号 0.7.3 → 0.8.0**

### Fix
- `routes.py` VALID_FETCH_PROVIDERS 补齐 mcp/site_crawler/deepwiki（API 400 → 正常）
- `models.py` ALL_SOURCES[fetch] 5→19（/sources 端点完整暴露）
- `source_registry.py` 补齐 3 个 fetch 注册（doctor/sources 完整覆盖）
- Panel useFetchPage.ts Provider 类型 + 4 套 FetchPage PROVIDERS 数组补齐

### Docs
- README / data-sources / configuration / api-reference / CHANGELOG / .env.example / souwen.example.yaml 全面更新

## v0.7.4

整合 PR #7 / #12 / #13 / #14 / #15 / #23 — 数据源数量从 66 增至 76，全链路同步（registry / models / routes / panel / CLI）。

### Feature
- **PR #7 — 飞书云文档**：新增 `feishu_drive` 源（`office` 分类），通过自建应用 App ID + App Secret 搜索企业飞书 / Lark 文档、表格、多维表格。
- **PR #12 — 智谱 AI Web Search Pro**：新增 `zhipuai` 源（`professional` 分类），含 AI 摘要与中文优化。配置项 `zhipuai_api_key`。
- **PR #13 — 阿里云 IQS（通义晓搜）**：新增 `aliyun_iqs` 源（`professional` 分类），LLM 优化的多源实时搜索 + AI 摘要。配置项 `aliyun_iqs_api_key`。
- **PR #14 — SiteCrawler + DeepWiki**：fetch 新增两个零配置提供者。
  - `site_crawler`：BFS 多页爬虫（参照 deepwiki-mcp `httpCrawler.ts` 复现），适合批量抓取整个文档站点。
  - `deepwiki`：抓取 deepwiki.com 上 GitHub 仓库的 AI 生成文档，使用 site_crawler + jina_reader 双策略。
- **PR #15 — HuggingFace Papers**：新增 `huggingface` 论文源，社区精选 + 语义搜索 + upvotes 热度排行，每篇均关联 arXiv ID。
- **PR #23 — Bing 增强 + fetch_content MCP 工具**：
  - 新增 `bing_cn` 源（必应中文 cn.bing.com），更适合中文检索场景。
  - MCP server 新增 `fetch_content` 工具，使 AI Agent 可直接通过 MCP 协议调用网页抓取（共 5 个 MCP 工具）。
- **本次集成审计**：
  - `ALL_SOURCES`（display）扩充至 66；`source_registry` 总计 76 条目。
  - fetch 提供者增至 19（含 `mcp` 协议提供者），跨 registry / models / routes / 4 套前端皮肤 / CLI 全部对齐。
  - 文档（README、`docs/data-sources.md`、`docs/configuration.md`、`docs/api-reference.md`）按当前实际数据源数量重写。

## v0.7.3

新增 11 个网页内容抓取提供者（总计 16 个）。

### Feature
- **Crawl4AI**：开源 Playwright 无头浏览器，适合 JS 重度页面（`pip install souwen[crawl4ai]`）
- **Scrapfly**：JS 渲染 + AI 提取 + 反爬绕过
- **Diffbot**：AI 结构化文章提取（作者、日期、元数据）
- **ScrapingBee**：代理池 + JS 渲染 + 反爬
- **ZenRows**：代理池 + JS 渲染 + 自动解析
- **ScraperAPI**：大规模代理池 + JS 渲染
- **Apify**：平台化 Actor 爬虫（4000+ 预构建任务）
- **Cloudflare Browser Rendering**：边缘浏览器渲染，直出 Markdown
- **Wayback Machine**：Internet Archive 存档快照（免费，无需 Key）
- **newspaper4k**：新闻文章专用提取（作者、日期、关键词、NLP 摘要，`pip install souwen[newspaper]`）
- **readability-lxml**：Mozilla Readability 算法（`pip install souwen[readability]`）
- 共享 HTML→Markdown 提取工具（`_html_extract.py`），供 HTML 返回型提供者复用
- 新增 `cloudflare_api_token` / `cloudflare_account_id` 配置字段
- 前端 4 皮肤 + CLI + API 全部同步支持 16 个提供者
- source_registry 新增 11 个 fetch 类注册条目

### Refactor
- **wayback** + **newspaper** 改为继承 `BaseScraper`，获得 curl_cffi TLS 指纹 + WARP 代理支持
  - wayback: 快照抓取走 BaseScraper（curl_cffi + WARP），可用性检查走 httpx
  - newspaper: HTML 抓取走 BaseScraper，newspaper4k 仅做解析（不再使用自带 requests）

## v0.7.1

Web 内容抓取功能增强与修复。

### Feature
- **网页内容抓取页面**：4 个皮肤（souwen-classic、carbon、apple、ios）新增 FetchPage，支持批量 URL 输入、多提供商选择（builtin/jina_reader/tavily/firecrawl/exa）、超时配置、结果导出。
- **内置抓取增强**：trafilatura 提取改为原生 Markdown 输出，支持链接、图片、表格保留。

### Breaking Change
- **`content_format` 字段变更**：内置抓取器（builtin fetcher）的 `FetchResult.content_format` 从 `"text"` 改为 `"markdown"`。下游消费者若依赖 `content_format == "text"` 分支需适配。

### Fix
- 修复 CJK（中日韩）内容因空格分词导致的误判过短问题
- 修复 `with_metadata=True` 导致 YAML front-matter 注入正文
- 修复 metadata 为 None 时丢弃有效提取内容
- 修复前端 30s 硬编码超时覆盖用户配置的超时值
- 修复 `final_url` 未校验协议导致的 XSS 风险
- 修复 `fetch.failed` i18n key 冲突
- 修复 apple/ios 皮肤大量硬编码英文字符串
- 新增前端 20 URL 上限校验
- 修复表单 label 缺少 htmlFor/id 关联
- 修复加载中按钮未禁用可重复提交

### Security
- **SSRF 重定向防护**：BuiltinFetcherClient 关闭自动重定向，手动跟踪每一跳并校验目标 IP，防止多跳 302 跳转到云元数据/内网地址
- BaseScraper 新增 `follow_redirects` 参数（默认 `True`，内置抓取器设为 `False`）
- Carbon 皮肤修复 i18n 插值缺失（`fetch.validUrls` 未传 `count` 参数）
- `pyproject.toml` 声明 `web` 可选依赖组（`trafilatura>=1.0`）

## v0.7.0

新增 8 个数据源 + 源分类体系重构。

### Feature
- **8 个新数据源**：GitHub Search、StackOverflow、Reddit、Bilibili、Wikipedia、YouTube、知乎、微博。覆盖代码仓库、问答社区、社交媒体、视频平台、百科全书五大类别。
- **integration_type 分类体系**：将原有的 `tier`（0/1/2）+ `is_scraper`（bool）双轴模型替换为单一的 `integration_type` 字符串字段：`open_api`（公开接口）、`scraper`（爬虫抓取）、`official_api`（授权接口）、`self_hosted`（自托管）。
- **source_registry 新增 `get_sources_by_integration_type()` 查询函数**。
- **CLI 增强**：`list_sources` 和 `sources` 表格新增集成类型列。

### Refactor
- `SourceMeta` dataclass 移除 `tier: int` 和 `is_scraper: bool` 字段，新增 `integration_type: str`；`is_scraper` 保留为计算属性。
- `doctor.py` 按集成类型分组报告，替代按 tier 分组。
- `routes.py` API 响应中 `tier`/`is_scraper` 替换为 `integration_type`（breaking change）。
- 前端 4 皮肤全面适配：徽章颜色、边框样式、矩阵视图均按集成类型区分。
- `tierBadgeColor()` → `integrationBadgeColor()`，`tierLabel()` → `integrationTypeLabel()`。

### Docs
- `souwen.example.yaml` 添加 8 个新数据源配置项。
- `api-reference.md` 更新 doctor 接口示例。
- 全量清理代码中残留的 tier 旧注释和文档引用。

### Test
- 新增 4 个 `TestSourceRegistryIntegrationType` 单元测试。
- `web_sources` 枚举测试扩展至 18 项。
- 总计 407 Python 测试 + 41 前端测试通过。

## v0.6.3

安全加固 + 前端美学升级。16 项安全/质量问题修复，4 皮肤视觉增强。

### Security
- **SSRF 防护**（`pdf_fetcher.py`）：URL 下载前做 DNS 解析 + CIDR 黑名单，阻断 `localhost`/`127.x`/`10.x`/`172.16-31.x`/`192.168.x`/`169.254.x` 等内网穿透。
- **时序安全认证**（`auth.py`）：消除 `check_search_auth()` 中的早期返回，visitor/admin 密码均用 `compare_digest()` 且结果在两次比较后才合并。
- **Sed 注入防护**（`warp-init.sh`）：对用户输入做 `sed` 元字符转义（反斜杠优先序）。
- **API Key 遮蔽**（`cli.py`）：`config show` 不再显示前 4 位明文。

### Fix
- **CSS Modules 后代选择器脆弱性**（`SourcesPage.module.scss` / `.tsx`，commit `6f11c6d`）：将 `.filterTabActive .filterTabCount` 后代选择器改为独立的 `.filterTabCountActive` 修饰符类，避免 CSS Modules 哈希变更时样式失效。
- **ETag RFC 合规**（`app.py`）：`_etag_matches()` 支持多值和 `*` 通配。
- **base_url 验证**（`routes.py`）：拒绝非 `http(s)://` 前缀。
- **atexit 死锁**（`google_patents.py`）：关闭回调加 5 秒超时。
- **session_cache 容错**（`session_cache.py`）：添加 `except` 日志，防止静默丢异常。
- **异步 I/O**（`pdf_fetcher.py`）：文件写入改用 `asyncio.to_thread()`。
- **惰性 Semaphore**（`web/search.py`）：避免事件循环外初始化。
- **退出码修正**（`cli.py`）：`CancelledError` 用 `exit(1)`。
- **日志 regex 扩展**（`logging_config.py`）：覆盖更多敏感字段名。
- **init 容错**（`cli.py`）：配置文件写入加 `try-except`。
- **去重复日志**（`routes.py`）：移除冗余异常日志。

### Style
- **四皮肤美学升级**：souwen-classic（多层阴影/hover 提升）、apple（毛玻璃/圆角）、carbon（辉光/扫描线）、ios（过渡动画/hairline 分割线）。23 文件 +200/−38 行。

### Docs
- **全代码库中文注释覆盖**：补齐 `src/souwen/**` 模块/类/函数的中文 docstring，统一注释风格，便于团队 onboarding 与 AI Agent 阅读。
- **README / CHANGELOG 准确性修复**：
  - 默认 Web 搜索引擎组合更正为 `DuckDuckGo + Bing`（与 `web/search.py:253` 实际默认值一致）。
  - 皮肤数量更新为 4 套（`souwen-classic` / `carbon` / `apple` / `ios`），同步构建/开发命令示例（含 `VITE_SKINS=apple|ios`）。
  - 配置章节新增双密码（`SOUWEN_VISITOR_PASSWORD` / `SOUWEN_ADMIN_PASSWORD`）说明，旧 `SOUWEN_API_PASSWORD` 标注为统一回退。
  - 零配置数据源数量从「22」更正为「18」（5 论文 + 2 专利 + 9 爬虫 + 2 自建）。

## v0.6.2

Docker/HFS 部署修复。单文件变更、无逻辑改动。

### Fix
- **Dockerfile**：`pip install ".[server]"` → `pip install ".[server,tls]"`。v0.6.0 将
  `curl-cffi` 从默认依赖移入 `[tls]` extras，但 Dockerfile 未同步更新，导致镜像构建
  阶段 `python -c "import curl_cffi"` 以 `ModuleNotFoundError` 失败（HuggingFace Spaces
  等基于 Dockerfile 的部署直接中断）。现同时安装 `server + tls` 两个 extras，保留专利
  爬虫/TLS 指纹反爬能力。

## v0.6.1

CLI/API Server 二轮评审后对功能缺陷、一致性、UX 的修复。均为向后兼容，非破坏性。

### CLI
- `--version` / `-V`：打印版本并退出（此前缺失）。
- 全局 `-v` / `-vv` / `-q`：控制日志级别（默认 WARNING，`-v`→INFO、`-vv`→DEBUG、`-q`→仅警告）。
- `Ctrl+C` 优雅退出：所有 `asyncio.run()` 调用统一走 `_run_async()`，捕获 `KeyboardInterrupt` / `CancelledError` 后 exit 130。
- `search paper/patent/web` 新增 `--timeout / -t`：端点硬超时（秒），超时 exit 124。
- `config show`：改为显示"已配置（前 4 位）"/"未配置"状态，不再完全隐藏。
- `serve` 启动摘要：输出密码保护/Admin 锁定/Docs/CORS/trusted_proxies/监听地址等关键配置。

### API Server
- 所有搜索端点 `q` 参数加 `min_length=1, max_length=500`（空串与超长请求由 422 拒绝）。
- 所有搜索端点（paper/patent/web）新增 `timeout` query 参数：超时返回 **504 gateway_timeout**。
- `/search/web` 补齐 `response_model=SearchWebResponse`，含 `meta(requested/succeeded/failed)`，与 paper/patent 对齐。
- `/search/web` 支持 `per_page` 别名（`max_results` 保留向后兼容）。
- 错误码映射扩展：500→`internal_error`、502→`bad_gateway`、503→`service_unavailable`、504→`gateway_timeout`。
- 限流 **429** 响应补齐 `X-RateLimit-Limit` / `X-RateLimit-Remaining` / `X-RateLimit-Reset` + `Retry-After`。
- 新增 `GET /readiness`：轻量就绪检查（不做网络），Kubernetes readiness probe 就绪。
- 面板 `panel.html` 响应加 `ETag` + `Cache-Control: public, max-age=3600`，支持 `If-None-Match` 304 命中（减少重发 860KB）。
- Lifespan 启动/关停时打印 WARP 状态（owner/mode/status），不干预外部进程。

### 测试
- 新增 `tests/test_cli.py`（5 个用例：version、help、config show、sources、Ctrl+C exit 130）。
- `tests/test_server.py` 追加 17 个用例（q 校验、per_page 别名、X-RateLimit 头、/readiness、panel ETag/304、timeout→504、状态码映射、WARP 启动日志）。
- 总计 **302 passed**（v0.6.0 基线 280 → +22）。

## v0.6.0

全面评审后批量修复 P0（阻塞）与 P1（重要）问题。详见 session plan.md。

### 破坏性变更
- **Admin 端点默认锁定**：未设置 `api_password` 且未显式 `SOUWEN_ADMIN_OPEN=1` 时，`/api/v1/admin/*` 返回 401（原先无密码即开放）。
- **`curl-cffi` 移出核心依赖**：改为可选 extras（`tls`、`scraper`）。依赖 TLS impersonation 的用户需 `pip install souwen[tls]`。
- **`/docs` 与 `/redoc` 默认关闭**：通过 `SOUWEN_EXPOSE_DOCS=1` 或 `expose_docs: true` 启用。
- **`retry.py` 签名变更**：`make_retry()` 接受 `retry_on` 白名单，默认异常集合外移为 `DEFAULT_*_EXCEPTIONS`。

### 并发与资源安全（P0）
- `search.py`：全局 `Semaphore(10)` 改为 per-event-loop 懒加载，修复跨事件循环共享导致的死锁/RuntimeError；新增 `SOUWEN_MAX_CONCURRENCY`。
- `http_client.py`：`OAuthClient._ensure_token` 增加 `asyncio.Lock` 防止并发刷新雷鸣群；`httpx.AsyncClient` 显式 `Limits(max_connections=100, max_keepalive=20, keepalive_expiry=30)`。
- `session_cache.py`：`_get_db` 双重检查锁防止并发建表；新增 `aclose()`；`get_session_cache()` 加 `threading.Lock`；应用 lifespan 收尾调用 `aclose()`。
- `patent/google_patents.py`：`_BrowserPool.shutdown()` 幂等 + `atexit` 注册，防止 Chromium 僵尸进程。

### 数据源健壮性（P0/P1）
- 新增 `_parsing.safe_parse_date`：统一容错 `None` / 空串 / `YYYY` / `YYYY-MM` / `YYYY-MM-DD` / ISO-T。`openalex`、`semantic_scholar`、`patentsview`、`pqai` 均切换到共享实现。
- Semantic Scholar：处理 429 `Retry-After`、401/403/503。
- 新增测试覆盖 429 / 401 / 503 / 缺失或畸形日期路径。

### 服务端安全（P0/P1）
- `server/limiter.py`：重写，参数校验、`deque(maxlen)` 有界、`get_client_ip(request, trusted_proxies)` 支持可信代理 XFF 解析。
- `server/app.py`：无密码时记录 WARN；`_panel_cache` 加锁；Warp reconcile 改为 `await`。
- `server/routes.py`：`/admin/ping` 输出最小化。
- `config.py`：新增 `trusted_proxies`、`expose_docs`；`SOUWEN_*` 支持逗号分隔 list。

### 日志与配置加固（P1）
- `logging_config.py`：`SensitiveDataFilter` 脱敏 `Bearer`/`token`/`api_key`/`password`。
- `config.py`：`_validate_proxy_url` 协议白名单（http/https/socks*），禁止 `file://`、`javascript:` 等；`resolve_proxy` 出口再校验。
- 面板 `authStore`：增加 `issuedAt` 和 30 分钟 TTL；`api.ts` 新增 `assertBaseUrlAllowed` + `VITE_ALLOWED_API_HOSTS` 白名单。

### 打包与 CI（P1）
- `pyproject.toml`：`curl-cffi` → `tls`/`scraper` extras；`dev` extras 添加 `pytest-cov`。
- `.github/workflows/ci.yml`：`pytest --cov` + codecov 上报；移除 `continue-on-error`。
- `.github/workflows/publish.yml`：`twine check` + tag 与版本号一致性校验。
- `tests/conftest.py`：autouse `get_config.cache_clear()` 夹具。
- `scraper/base.py`：Playwright `ImportError` 改为日志降级，不再硬崩溃。

### 测试
- 新增并发测试（`test_search.py`、`test_infra.py`、`test_session_cache.py`），新增 `test_logging.py`（11）、`test_config.py::TestProxyValidation`（7）、`test_semantic_scholar.py`（8）、`test_server.py` 服务端鉴权/限流/白名单（11）。
- 总计 **280 passed**（基线 215）。

## v0.5.0

### 新增
- **运行时皮肤切换**：支持在不同皮肤间实时切换（需页面刷新），不再需要重新构建
  - Skin Registry 模式：`registerSkin()` / `getActiveSkin()` / `listSkinIds()`
  - Vite 虚拟模块 `virtual:skin-loader` 按 `VITE_SKINS` 环境变量加载
  - CSS 命名空间隔离：`html[data-skin='xxx']` 作用域
- **皮肤切换下拉面板**：替代原有的循环按钮，显示皮肤名称、描述、选中状态
- **Carbon 真正浅色模式**：白色背景、深色文字、适当对比度（原有"浅色"仅为稍浅的深色）
- **经典皮肤宽度优化**：内容最大宽度从 1200px 提升到 1520px
- **全界面作者信息**：所有页面展示 @BlueSkyXN、项目地址、GPLv3 协议
- 皮肤切换时自动重置模式和配色方案为目标皮肤默认值
- 下拉面板支持 Escape 键关闭和点击外部关闭
- 下拉面板增加 `aria-expanded`、`aria-haspopup` 无障碍属性
- 所有硬编码颜色替换为 CSS 变量（grid-line、hero-glow、overlay-bg 等）

### 修复
- 修复皮肤切换后渲染错误组件的 bug（ES 模块提升导致）
- Docker 构建支持 `SKINS` 参数配置
- `ruff format` 格式化 10 个 Python 文件，CI 不再失败

### 文档
- README 添加作者信息、项目地址、GPLv3 协议
- CHANGELOG 更新至 v0.5.0
- pyproject.toml 作者信息更新为 @BlueSkyXN

## v0.4.0

### 新增
- 11 个新搜索引擎：SerpAPI、Firecrawl、Perplexity Sonar、Linkup、ScrapingDog、Startpage、Baidu、Mojeek、Yandex、Whoogle、Websurfx
- 67 个 mock 测试（pytest-httpx），覆盖 OpenAlex、Crossref、ArXiv、PatentsView、PQAI、Web 聚合搜索
- 代理池轮换（`proxy_pool` 配置 + 随机选取）
- Playwright 浏览器实例池化（`_BrowserPool` 单例复用 Chromium）
- 抽象限流器接口 `RateLimiterBase(ABC)`，支持 Redis 等分布式限流器扩展
- 全局并发度控制 `asyncio.Semaphore(10)`，防止连接过载
- CLI 搜索结果显示失败源警告
- **前端管理面板全面重设计**：参照 Apple/Google 设计语言，升级 UI/UX
  - Command Center 搜索页布局（居中英雄区、渐变光球、建议标签、⌘K 快捷键）
  - 仪表盘页增强（渐变统计卡片、健康环形图、脉动状态指示器）
  - 数据源页增强（彩色左边框、层级徽章、状态指示器）
  - 配置页增强（毛玻璃卡片、微光按钮动画、分组显示）
  - 无密码时自动登录
- **前端视觉主题系统**：支持 3 种强调色方案（星云 Nebula / 极光 Aurora / 黑曜石 Obsidian），明暗模式切换
- **前端多皮肤架构**：core/ + skins/ 分层，支持构建时选择皮肤
  - 共享层（core/）：stores、API 客户端、类型定义、i18n、工具函数
  - 皮肤层（skins/）：完全独立的组件、页面、样式、路由
  - 三层分离：Skin（构建时）→ Mode（运行时明暗）→ Scheme（运行时配色）
  - Vite 路径别名：`@core` / `@skin`，通过 `VITE_SKIN` 环境变量选择皮肤
- **Docker 多阶段构建**：新增 Node.js 构建阶段，支持 `--build-arg SKIN=xxx` 选择前端皮肤

### 修复
- 所有 8 个论文客户端 `total=` → `total_results=`（Pydantic v2 静默忽略 bug）
- 所有 8 个论文客户端 `extra=` → `raw=`（元数据丢失 bug）
- OpenAlex 配置字段名 `openalex_mailto` → `openalex_email`
- ConfigError 构造函数签名错误（TypeError 崩溃）
- ArXiv/PubMed XML 解析崩溃保护（try/except ET.ParseError）
- PubMed 整数转换、除零、分页计算
- Google URL 解码空值 IndexError
- Scraper Retry-After 解析崩溃 + 120s 上限
- EPO OPS range 计算安全
- PDF 获取器 BOM 容忍、窄异常捕获
- YAML 配置加载器支持嵌套和扁平两种格式

### 改进
- 会话缓存从同步 sqlite3 迁移到异步 aiosqlite
- 浏览器指纹库从 3 个扩展到 10 个（Chrome + Edge + Safari + Android）
- 异常处理区分 ConfigError / RateLimitError / 其他
- 所有论文客户端填充 journal/venue 字段
- Pydantic 模型添加 `extra="forbid"` 防止字段名拼写错误
- 统一版本号为单一来源 `__version__`
- Web API 客户端添加 JSON 解析保护
- 数据源列表抽取为共享常量 `ALL_SOURCES`
- HTTP-date Retry-After 解析兼容
- OAuth 响应 KeyError 保护
- TokenBucketLimiter rate 合法性校验

### 依赖
- 新增 `aiosqlite>=0.20.0`

## v0.3.0

### 新功能
- **YAML 配置**: 支持 `souwen.yaml` 配置文件，优先级 env > yaml > .env > 默认值
- **CLI 工具**: `souwen` 命令行工具，支持 `search paper/patent/web`, `config show/init`, `sources`, `serve`
- **FastAPI 服务**: REST API 端点 `/api/v1/search/{paper,patent,web}`, OpenAPI 文档自动生成
- **统一搜索门面**: `search()`, `search_papers()`, `search_patents()` 一个函数搞定
- **web_search() 增强**: engine_map 补全全部 10 个引擎（5 爬虫 + 5 API）

### 修复
- 版本号统一为 0.3.0（pyproject.toml / __init__.py / User-Agent）
- ruff 未使用导入修复

### 依赖
- 新增: `typer>=0.12`, `pyyaml>=6.0`
- 新增可选: `fastapi>=0.111`, `uvicorn[standard]>=0.29`（server extras）

## [0.2.0] - 2026-04-04

### Added
- **常规网页搜索模块** (`souwen.web`) — 10 个搜索引擎
  - **爬虫类（无需 Key，零配置即用）**
    - DuckDuckGoClient — DuckDuckGo HTML 搜索（uddg= URL 解码）
    - YahooClient — Yahoo 搜索（Bing 驱动，RU=/RK= URL 解码）
    - BraveClient — Brave 独立索引搜索
    - GoogleClient — Google 搜索（高风险，TLS 指纹 + 多 snippet 选择器）
    - BingClient — Bing 搜索（li.b_algo 选择器）
  - **API 类（需 Key / 自建实例）**
    - SearXNGClient — SearXNG 元搜索（一个接入 = 250+ 引擎）
    - TavilyClient — Tavily AI 搜索（为 Agent 设计，内置内容提取）
    - ExaClient — Exa 语义搜索（神经索引 + find_similar）
    - SerperClient — Serper Google SERP API（含 Knowledge Graph）
    - BraveApiClient — Brave 官方 REST API（免费 2000 次/月）
  - `web_search()` — 并发多引擎聚合搜索（asyncio.gather + URL 去重）
- **新数据模型**
  - `WebSearchResult` — 统一网页搜索结果模型
  - 10 个 `SourceType.WEB_*` 枚举值
- **新配置项**
  - `searxng_url` / `tavily_api_key` / `exa_api_key` / `serper_api_key` / `brave_api_key`
- **过盾特性**
  - 所有爬虫引擎基于 `BaseScraper`（curl_cffi TLS 指纹 + 浏览器头）
  - Google/Bing 专门调优延迟和重试策略

### Fixed
- `BaseScraper.close()` 中 curl_cffi `AsyncSession.close()` 缺少 `await`（资源泄漏）

## [0.1.0] - 2026-04-03

### Added
- 项目初始化
- **基础设施层**
  - `config.py` — 统一配置管理（环境变量 / .env / 默认值）
  - `models.py` — Pydantic v2 统一数据模型（PaperResult, PatentResult, SearchResponse）
  - `exceptions.py` — 6 类自定义异常体系
  - `rate_limiter.py` — 令牌桶 + 滑动窗口限流器
  - `http_client.py` — httpx async 统一客户端 + OAuth 2.0 Token 自动管理
- **8 个论文数据源**
  - OpenAlex (无需 Key)
  - Semantic Scholar (可选 Key，含 TLDR)
  - Crossref (无需 Key，DOI 权威源)
  - arXiv (无需 Key，Atom XML 解析，全文免费)
  - DBLP (无需 Key，计算机科学权威)
  - CORE (需 Key，开放获取)
  - PubMed (可选 Key，两步 XML 检索)
  - Unpaywall (需 Email，OA PDF 查找)
  - PDF 回退链获取器 (5 级降级策略)
- **8 个专利数据源**
  - PatentsView (无需 Key，USPTO 数据)
  - PQAI (无需 Key，语义检索)
  - EPO OPS (OAuth 2.0，CQL 检索)
  - USPTO ODP (API Key)
  - The Lens (Bearer Token，动态限流)
  - CNIPA (OAuth 2.0，中国专利)
  - PatSnap (API Key，172 司法管辖区)
  - Google Patents (爬虫兜底)
- **爬虫层**
  - `BaseScraper` — 礼貌爬取基类（自适应限速、UA 轮换）
  - `GooglePatentsScraper` — Google Patents 爬虫实现
- **示例和测试**
  - `examples/search_papers.py` — 论文搜索示例
  - `examples/search_patents.py` — 专利搜索示例
  - 15 个基础设施层单元测试
