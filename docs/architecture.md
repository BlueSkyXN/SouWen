# 架构设计

> SouWen 的内部架构、数据流与设计原则

## 总体架构

SouWen 采用**搜索门面（Search Facade）**模式，通过统一入口分发请求到 37 个异构数据源，并将结果归一化为统一的 Pydantic v2 数据模型。

```
User / AI Agent
       │
       ▼
  search(query, domain)          ← 统一入口 (search.py)
       │
  ┌────┼────────────┐
  ▼    ▼            ▼
search_papers  search_patents  web_search
  │              │               │
  ▼              ▼               ▼
_search_source_limited()         ← asyncio.Semaphore(10) 全局并发控制
  │
  ▼
_run_client(ClientClass, "search", **kwargs)
  │
  ▼
async with ClientClass() as client:
    response = await client.search(...)   ← 各数据源客户端
  │
  ▼
SearchResponse(results=[PaperResult | PatentResult | WebSearchResult])
```

## 数据流

1. **用户调用** `search(query, domain="paper")` 或直接调用 `search_papers()`
2. **门面层** 根据 domain 路由到对应的搜索函数
3. **并发控制** `_search_source_limited()` 通过 `asyncio.Semaphore(10)` 防止连接过载
4. **客户端实例化** `_run_client()` 使用 async context manager 创建客户端并调用搜索方法
5. **HTTP 请求** 客户端通过 `SouWenHttpClient`（API 类）或 `BaseScraper`（爬虫类）发送请求
6. **结果解析** 各客户端将原始 JSON/HTML 解析为统一的 `PaperResult` / `PatentResult` / `WebSearchResult`
7. **异常隔离** 每个数据源独立捕获异常，失败不影响其他源

## 两种基类模式

### SouWenHttpClient（API 类数据源）

用于有正式 REST API 的数据源（OpenAlex、Crossref、Semantic Scholar 等）。

```python
SouWenHttpClient(
    base_url: str = "",
    headers: dict[str, str] | None = None,
    timeout: int | None = None,       # 默认取 config.timeout
    max_retries: int | None = None    # 默认取 config.max_retries
)
```

特性：
- `async get()` / `async post()` 封装 httpx 异步请求
- `@retry` 装饰器：3 次重试，指数退避 2-10s
- HTTP 状态码自动映射异常：401/403 → `AuthError`，429 → `RateLimitError`，5xx → `SourceUnavailableError`
- 支持 `async with` 上下文管理器

**OAuthClient(SouWenHttpClient)** 扩展了 OAuth 2.0 自动管理：
- `_ensure_token()` 自动获取和缓存 Bearer Token
- Token 过期前 60s 自动刷新
- 通过 `SessionCache`（aiosqlite）持久化 Token

### BaseScraper（爬虫类数据源）

用于无正式 API 的数据源（DuckDuckGo、Google、Bing 等搜索引擎）。

```python
BaseScraper(
    min_delay: float = 2.0,       # 最小请求间隔
    max_delay: float = 5.0,       # 最大请求间隔
    max_retries: int = 3,
    use_curl_cffi: bool | None = None  # 自动检测
)
```

特性：
- **TLS 指纹模拟**：优先使用 curl_cffi 模拟 Chrome JA3 指纹
- **浏览器请求头**：13 个头（Sec-CH-UA 系列、Sec-Fetch 系列等）
- **礼貌爬取**：随机延迟 + 自适应退避
- **429 处理**：退避倍数 ×2（最大 16×），成功后 ×0.8 渐进恢复
- 未安装 curl_cffi 时自动回退到 httpx

## 限流器架构

```
RateLimiterBase(ABC)
├── TokenBucketLimiter    固定速率限流（如 PatentsView 45次/分钟）
└── SlidingWindowLimiter  动态窗口限流（可根据响应头动态调整）
```

### TokenBucketLimiter

令牌桶算法，适用于固定速率限制：

```python
TokenBucketLimiter(rate=0.75, burst=1)  # 0.75 req/s = 45 req/min
```

- `_tokens` 浮点计数，范围 0 到 burst
- `acquire()` 等待令牌可用后消耗 1 个
- `_refill()` 按时间流逝 × rate 补充令牌

### SlidingWindowLimiter

滑动窗口算法，适用于需要根据响应头动态调整的场景：

```python
SlidingWindowLimiter(max_requests=100, window_seconds=60.0)
```

- 维护 `deque[float]` 时间戳队列
- `update_from_headers(remaining, retry_after)` 支持从响应头动态调整

### 扩展接口

`RateLimiterBase(ABC)` 支持自定义实现，例如 Redis 分布式限流器：

```python
class RedisRateLimiter(RateLimiterBase):
    async def acquire(self):
        # 使用 Redis Lua 脚本实现原子计数 + 过期
        ...
```

## 异常体系

```
SouWenError (base)
├── ConfigError            缺少 API Key 等配置错误
├── AuthError              401/403 认证失败
├── RateLimitError         429 限流（包含 retry_after）
├── SourceUnavailableError 5xx 或网络错误
├── ParseError             JSON/HTML 解析失败
└── NotFoundError          无结果
```

多源搜索中，每个数据源独立捕获异常：
- `ConfigError` → 跳过并记录 info（缺 Key 属预期行为）
- `RateLimitError` → 跳过并记录 warning
- 其他异常 → 跳过并记录 warning

## 重试策略（分层）

| 级别 | 装饰器 | 次数 | 退避 | 适用场景 |
|------|--------|------|------|----------|
| L1 | `http_retry` | 3 | 2-10s 指数 | 常规 API 请求 |
| L2 | `scraper_retry` | 5 | 5-30s 指数 | 网页爬取 |
| L3 | `captcha_retry` | 5 | 5-30s 指数 | CAPTCHA 场景 |
| L4 | `poll_retry` | 可配置 | 固定间隔 | 异步任务轮询 |

## 会话缓存（aiosqlite）

`SessionCache` 使用异步 SQLite 持久化 OAuth Token 和 Cookie：

- **数据库位置**：`~/.local/share/souwen/session_cache.db`
- **sessions 表**：网站会话数据（Cookie、Header），支持 TTL
- **oauth_tokens 表**：OAuth 2.0 Token（access_token、refresh_token、expires_at）
- Token 提前 60s 过期，避免边界情况
- 全异步操作（aiosqlite），首次导入时同步建表

## 项目结构

```
SouWen/
├── .github/workflows/     # CI/CD (lint + test + publish)
├── pyproject.toml
├── .env.example
├── souwen.example.yaml
├── src/souwen/
│   ├── __init__.py         # 公开 API 导出
│   ├── search.py           # 搜索门面（search, search_papers, search_patents）
│   ├── config.py           # 统一配置管理
│   ├── models.py           # Pydantic v2 统一数据模型
│   ├── exceptions.py       # 6 类自定义异常体系
│   ├── rate_limiter.py     # 限流器（令牌桶 + 滑动窗口）
│   ├── http_client.py      # httpx async + OAuth 2.0 Token 自动刷新
│   ├── fingerprint.py      # Chrome TLS 指纹库
│   ├── session_cache.py    # SQLite 会话/Token 持久化缓存
│   ├── retry.py            # 分层重试策略
│   ├── doctor.py           # 健康检查 / 诊断
│   ├── cli.py              # Typer CLI 命令
│   ├── paper/              # 8 个论文数据源
│   ├── patent/             # 8 个专利数据源
│   ├── web/                # 21 个搜索引擎（9 爬虫 + 10 API + 2 自建）
│   ├── scraper/            # 爬虫基础层（TLS 指纹 + 礼貌爬取）
│   ├── server/             # FastAPI 服务
│   │   └── panel.html      # 前端构建产物（单文件 HTML）
│   └── integrations/       # MCP Server 集成
├── panel/                  # 前端源码（React + TypeScript）
│   └── src/
│       ├── core/           # 跨皮肤共享层
│       └── skins/          # 皮肤层（每个皮肤完全独立的 UI）
├── tests/                  # 单元测试
├── examples/               # 使用示例
├── docs/                   # 项目文档
└── local/                  # 设计文档（不纳入包）
```

## 前端架构（管理面板）

管理面板采用**多皮肤架构**，分为共享核心层和独立皮肤层。

### 三层分离模型

```
Skin（皮肤）→ Mode（模式）→ Scheme（配色）
│                │              │
│                │              └── 每皮肤独立配色（运行时切换）
│                └── light / dark（运行时切换）
└── souwen-classic / carbon / ...（运行时切换，或单皮肤构建）
```

- **Skin（皮肤）**：完全独立的前端 UI——不同的布局、组件、路由、交互逻辑。默认全皮肤构建，支持运行时切换；也可通过 `VITE_SKINS` 环境变量指定单皮肤构建。
- **Mode（模式）**：明暗模式（light/dark），用户在面板内实时切换。
- **Scheme（配色方案）**：强调色方案，每个皮肤可定义自己支持的配色集。

### 共享层（core/）

跨皮肤共享的非 UI 模块：

| 模块 | 用途 |
|------|------|
| `core/stores/` | Zustand 状态管理（authStore, notificationStore） |
| `core/services/` | API 客户端（封装 fetch，统一错误处理） |
| `core/types/` | TypeScript 类型定义（API 响应模型、共享类型） |
| `core/i18n/` | 国际化（i18next，当前支持中文） |
| `core/lib/` | 工具函数（动画预设、数据归一化、错误处理） |
| `core/styles/` | 共享 CSS 重置与基础样式（`base.scss`） |
| `core/test/` | 共享测试工具与测试用例 |

### 皮肤层（skins/）

每个皮肤是一个完全自包含的前端应用：

```
skins/souwen-classic/
├── index.ts           # 皮肤入口（导出 AppShell, LoginPage, routes, config, bootstrap）
├── skin.config.ts     # 皮肤配置（配色方案、默认模式等）
├── routes.tsx         # 路由定义
├── stores/            # 皮肤状态（skinStore：mode/scheme 管理）
├── components/
│   ├── layout/        # 布局组件（MainLayout, Sidebar, Header）
│   └── common/        # 通用 UI 组件（Button, Card, Modal, Toast, ErrorBoundary, Spinner）
├── pages/             # 页面（Dashboard, Search, Sources, Config, Login）
├── styles/            # SCSS 样式（全局 token，通过 html[data-skin] 命名空间隔离）
└── test/              # 皮肤专属测试
```

### 构建系统

- **Vite + vite-plugin-singlefile** → 打包为单个 `index.html`，复制到 `src/souwen/server/panel.html`
- **虚拟模块**：`virtual:skin-loader` 根据 `VITE_SKINS` 导入并注册指定皮肤
- **皮肤注册表**：`core/skin-registry.ts` 管理运行时皮肤注册、查找、切换
- **路径别名**：`@core` → `src/core`
- **默认全皮肤构建**：`npm run build`（等同于 `VITE_SKINS=all`）
- **单皮肤构建**：`npm run build:classic` 或 `VITE_SKINS=souwen-classic npm run build`

### CSS 架构

- **SCSS Modules**：组件样式通过 CSS Modules 隔离（`.module.scss`）
- **CSS 自定义属性**：全局 token（`--accent`、`--bg`、`--card-bg` 等）通过 `html[data-skin]`、`[data-mode]` 和 `[data-scheme]` 选择器切换
- **皮肤级 CSS 隔离**：每个皮肤的 `global.scss` 使用 `html[data-skin='xxx']` 命名空间，多皮肤共存时互不干扰
- **无 Tailwind**：项目使用纯 SCSS + CSS Variables

### 状态管理

| Store | 位置 | 用途 |
|-------|------|------|
| `useAuthStore` | core/ | 登录状态、token、版本号 |
| `useNotificationStore` | core/ | Toast 通知 |
| `useSkinStore` | skin/ | 明暗模式、配色方案、localStorage 持久化 |

HTML 属性映射：`data-mode`（light/dark）、`data-scheme`（nebula/aurora/obsidian）

## 设计原则

1. **AI Agent 友好**：统一数据模型，结构化输出，最小化 Token 消耗
2. **渐进式配置**：无需 Key 的数据源开箱即用，需要 Key 的友好报错并给出注册指引
3. **稳健性**：自动重试、限流保护、优雅降级
4. **可观测性**：结构化日志，请求耗时追踪

## 近期改进（v0.3.0）

- **11 个新搜索引擎**：SerpAPI、Firecrawl、Perplexity Sonar、Linkup、ScrapingDog、Startpage、Baidu、Mojeek、Yandex、Whoogle、Websurfx
- **异步会话缓存**：从同步 sqlite3 迁移到 aiosqlite
- **全局并发控制**：`asyncio.Semaphore(10)` 防止连接过载
- **Playwright 浏览器池化**：`_BrowserPool` 单例复用 Chromium 实例
- **代理池轮换**：支持多代理 URL 配置 + 随机选取
- **扩展浏览器指纹库**：从 3 个扩展到 10 个（Chrome + Edge + Safari + Android）
- **抽象限流器接口**：`RateLimiterBase(ABC)` 支持 Redis 等分布式限流器扩展
- **204 个自动化测试**：含 mock 测试（pytest-httpx）
- **CLI 搜索改进**：搜索结果显示失败源警告
- **Pydantic 模型加固**：`extra="forbid"` 防止字段名拼写错误
- **数据源常量**：`ALL_SOURCES` 共享常量，统一版本号为单一来源 `__version__`
