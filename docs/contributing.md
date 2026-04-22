# 贡献指南

> 如何为 SouWen 贡献代码

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen

# 安装开发依赖
pip install -e ".[dev]"

# 安装爬虫可选依赖（TLS 指纹模拟）
pip install -e ".[scraper]"

# 安装 Playwright 浏览器
playwright install chromium
```

## 运行测试

```bash
# 运行全部后端测试
pytest tests/ -v

# 快速运行
pytest tests/ -q --tb=short

# 运行前端测试
cd panel && npm test

# 运行示例脚本
python examples/search_papers.py
python examples/search_patents.py
python examples/search_web.py
```

## 前端开发

管理面板位于 `panel/` 目录，使用 React + TypeScript + SCSS Modules + Framer Motion。

### 环境搭建

```bash
cd panel
npm install
npm run dev              # 启动开发服务器（默认全皮肤，可运行时切换）
npm run dev:classic      # 单皮肤开发
```

### 目录结构

```
panel/src/
  core/                  # 跨皮肤共享（stores, API, types, i18n, skin-registry）
    styles/base.scss     # 共享 CSS 重置
    skin-registry.ts     # 运行时皮肤注册表
  skins/
    souwen-classic/      # 经典皮肤
      components/        # UI 组件（含 ErrorBoundary, Toast, Spinner）
      pages/             # 页面
      styles/            # SCSS 样式（通过 html[data-skin] 命名空间隔离）
      stores/            # 皮肤状态管理
      routes.tsx         # 路由定义
      skin.config.ts     # 皮肤配置（配色方案、默认模式）
      index.ts           # 皮肤入口（导出 SkinModule 接口 + bootstrap）
    carbon/              # 终端风格皮肤
    apple/               # Apple HIG 灵感皮肤
    ios/                 # macOS Settings / iOS 灵感皮肤
```

### 构建

```bash
npm run build            # 默认全皮肤构建
npm run build:classic    # 单皮肤构建（体积更小）
# 产物：单文件 dist/index.html，自动复制到 src/souwen/server/panel.html
```

### 创建新皮肤

1. 复制 `panel/src/skins/souwen-classic/` 为新目录（如 `skins/my-skin/`）
2. 修改 `skin.config.ts` 中的皮肤元信息和配色方案
3. 确保 `index.ts` 导出完整的 `SkinModule` 接口（含 `bootstrap`、`ErrorBoundary`、`Spinner`）
4. CSS 使用 `html[data-skin='my-skin']` 命名空间
5. 在 `vite.config.ts` 的 `ALL_SKINS` 数组中注册
6. 构建：`VITE_SKINS=my-skin npm run build`

### 注意事项

- 使用 `@core/...` 引用共享模块
- 皮肤之间不可互相引用，只能引用 `@core`
- 动画使用 Framer Motion：导入 `m`（不是 `motion`），`type: 'spring'` 需要 `as const`
- SCSS 变量定义在 `styles/variables.scss`，全局 token 通过 CSS 自定义属性
- 不使用 Tailwind — 项目使用 SCSS Modules + CSS Variables

## 代码风格

- **格式化工具**：[Ruff](https://docs.astral.sh/ruff/)
- **行宽限制**：100 字符
- **Python 版本**：≥ 3.10（使用 `X | Y` 类型联合语法）
- **类型注解**：全面使用类型注解

```bash
# 代码检查
ruff check src/

# 格式检查
ruff format --check src/

# 自动修复
ruff check --fix src/
ruff format src/
```

## 添加新数据源（V1）

V1 把 v0 时代分散的"7 处修改"压缩到 **1-2 处**：

1. 实现 `Client` 类（继承 `SouWenHttpClient` / `OAuthClient` / `BaseScraper`）。
2. 在 `src/souwen/registry/sources.py` 添加一个 `_reg(SourceAdapter(...))`。
3. 若需要 API Key，在 `src/souwen/config.py` 的 `SouWenConfig` 加字段并在 adapter 里通过 `config_field="..."` 引用。

完整步骤、模板与一致性测试要求请看 **[adding-a-source.md](./adding-a-source.md)**。

> 注意：V1 注册表会被 `tests/registry/test_consistency.py` 守护——`client_loader` 指向的类、`MethodSpec.method_name`、`param_map` 的目标参数、`config_field` 是否在 `SouWenConfig` 中存在等都会被自动校验，新增源**必须**让该测试通过。

## V0 / V1 兼容规则

V1 重构期间（v0.9.x 过渡版本）必须保持以下兼容性：

- ✅ **保留 v0 公开入口**：`souwen.search.search_papers / search_patents / web_search`、`souwen.web.fetch.fetch_content`、`souwen.web.wayback.WaybackClient` 等仍然可用，内部转发到 `souwen.facade.*`。
- ✅ **保留 `souwen.models.SourceType` 与 `ALL_SOURCES`**：现在由 `registry.views.enum_values()` / `as_all_sources_dict()` 派生，但导出名不变。
- ✅ **保留 v0 配置字段**：`SouWenConfig` 的所有 flat key（如 `tavily_api_key`）在 V1 仍可用；新增源若选用 flat key 需同时支持 `sources.<name>.api_key` 频道覆盖。
- ✅ **shim 模块**：`souwen.scraper.base` / `souwen.http_client` / `souwen.fingerprint` 仍存在，内部 `from souwen.core.* import *`。请在新代码中**优先使用 `souwen.core.*` 路径**。
- ❌ **不要新增 v0 风格的 dispatcher dict**：搜索路由、`source_map`、`engine_map` 等都已下沉到 registry 派发，新源不要再去改 `search.py` / `web/search.py`。
- ❌ **不要绕过 registry**：CLI / 服务端 / MCP / 文档生成都应通过 `souwen.registry` 查询，避免再次出现"信息散落 7 处"的旧问题。

## 提交规范（Conventional Commits）

提交信息遵循 [Conventional Commits 1.0](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

常用 `type`：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`。`scope` 推荐使用 domain 名（`paper` / `patent` / `web` / `social` / `video` / `registry` / `facade` / `panel` / `docker` 等）。

示例：

```
feat(registry): add aliyun_iqs as web search provider
fix(scraper): retry on curl_cffi connection reset
docs(api): document /api/v1/sitemap endpoint
refactor(core): move BaseScraper into core/scraper
```

## 分支策略

- `main` — 受保护的发布分支，CI 必须全绿才能合并。
- `feat/*` `fix/*` `docs/*` — 特性 / 缺陷 / 文档分支，从 `main` 切出，PR 合并后删除。
- 重大重构（如 V1）使用专门的长寿命分支，期间通过 RFC 文档（`local/`）跟踪决策。

## PR 流程

1. Fork 仓库并创建特性分支
2. 确保所有测试通过：`pytest tests/ -v`
3. 确保代码风格合规：`ruff check src/ && ruff format --check src/`
4. 提交 PR，描述清楚改动内容和动机
5. CI 会自动运行 lint + test
