# API 接口参考

> SouWen 公开 API、数据模型、CLI 命令与 MCP 工具

> **V1 架构提示**：所有路由都派发到 `souwen.facade.*`（统一门面层），门面再通过 `souwen.registry`（单一事实源）挑选 Client。新增数据源不需要改路由，参见 [adding-a-source.md](./adding-a-source.md)。

> **⚠️ 声明：本项目仅供 Python 学习与技术研究使用。**
> 涵盖的学习方向包括：API 对接与聚合、全栈开发（FastAPI + React）、爬虫技术（TLS 指纹 / 浏览器池化 / 反爬绕过）、CLI 开发（Rich / Click）、异步编程（asyncio / httpx）等。
> 请勿将本项目用于任何违反相关法律法规或第三方服务条款的用途。

## Python API

### 统一搜索入口

```python
from souwen import search, search_papers, search_patents, web_search
```

#### `search(query, domain="paper", **kwargs)` → `list[SearchResponse]`

统一调度器，根据 `domain` 路由到对应搜索函数。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `domain` | `str` | `"paper"` | `"paper"` / `"patent"` / `"web"` |
| `**kwargs` | — | — | 传递给对应搜索函数 |

#### `search_papers(query, sources=None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源论文搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `sources` | `list[str] \| None` | `["openalex", "crossref", "arxiv", "dblp", "pubmed"]` | 数据源列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `search_patents(query, sources=None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源专利搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `sources` | `list[str] \| None` | `["google_patents"]` | 数据源列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `web_search(query, engines=None, max_results_per_engine=10)` → `WebSearchResponse`

并发多引擎网页搜索 + URL 去重。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `engines` | `list[str] \| None` | `["duckduckgo", "bing"]` | 引擎列表 |
| `max_results_per_engine` | `int` | `10` | 每个引擎最大结果数 |

### 网页内容抓取

```python
from souwen.web.fetch import fetch_content, validate_fetch_url
```

#### `fetch_content(urls, providers=None, timeout=30.0, skip_ssrf_check=False)` → `FetchResponse`

并发内容抓取，支持 19 个提供者。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | `list[str]` | — | 目标 URL 列表 |
| `providers` | `list[str] \| None` | `["builtin"]` | 提供者: builtin / jina_reader / tavily / firecrawl / exa / crawl4ai / scrapfly / diffbot / scrapingbee / zenrows / scraperapi / apify / cloudflare / wayback / newspaper / readability / mcp / site_crawler / deepwiki |
| `timeout` | `float` | `30.0` | 每个 URL 超时秒数 |
| `skip_ssrf_check` | `bool` | `False` | 跳过 SSRF 校验（仅内部使用） |

#### `validate_fetch_url(url)` → `tuple[bool, str]`

SSRF 防护 URL 校验（DNS 解析 + 私有/保留 IP 拦截）。

### 配置管理

```python
from souwen import get_config, reload_config
```

#### `get_config()` → `SouWenConfig`

获取全局配置单例（`@lru_cache` 缓存）。

#### `reload_config()` → `SouWenConfig`

清除缓存并重新加载配置。

### PDF 全文获取

```python
from souwen.paper import fetch_pdf
```

#### `fetch_pdf(paper)` → `Path | None`

5 级回退链自动获取论文 PDF：

1. `paper.pdf_url` 直接下载
2. Unpaywall OA 查询
3. CORE 全文查询
4. DOI 重定向解析
5. Sci-Hub 回退

## 数据模型

### PaperResult

```python
class PaperResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    authors: list[Author]           # 作者列表
    abstract: str | None            # 摘要
    doi: str | None                 # DOI
    year: int | None                # 发表年份
    publication_date: date | None   # 发表日期
    journal: str | None             # 期刊
    venue: str | None               # 会议/期刊
    citation_count: int | None      # 引用次数
    open_access_url: str | None     # OA 链接
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    tldr: str | None                # TLDR 摘要（Semantic Scholar）
    raw: dict                       # 原始响应
```

### PatentResult

```python
class PatentResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    patent_id: str                  # 公开号/申请号
    application_number: str | None  # 申请号
    publication_date: date | None   # 公开日
    filing_date: date | None        # 申请日
    applicants: list[Applicant]     # 申请人
    inventors: list[str]            # 发明人
    abstract: str | None            # 摘要
    claims: str | None              # 权利要求
    ipc_codes: list[str]            # IPC 分类号
    cpc_codes: list[str]            # CPC 分类号
    family_id: str | None           # 专利族 ID
    legal_status: str | None        # 法律状态
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    raw: dict                       # 原始响应
```

### WebSearchResult

```python
class WebSearchResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    url: str                        # 链接
    snippet: str                    # 摘要片段
    engine: str                     # 搜索引擎名
    raw: dict                       # 原始响应
```

### FetchResult

```python
class FetchResult(BaseModel):
    url: str                                    # 请求 URL
    final_url: str                              # 重定向后最终 URL
    title: str = ""                             # 页面标题
    content: str = ""                           # 提取正文（优先 Markdown）
    content_format: Literal["markdown", "text", "html"] = "markdown"
    source: str = ""                            # 提供者标识
    snippet: str = ""                           # 摘要（前 500 字）
    published_date: str | None = None           # 发布日期
    author: str | None = None                   # 作者
    error: str | None = None                    # 错误信息（无错误为 None）
    raw: dict = {}                              # 原始响应
```

### FetchResponse

```python
class FetchResponse(BaseModel):
    urls: list[str]                             # 请求 URL 列表
    results: list[FetchResult]                  # 抓取结果
    total: int = 0                              # 总数
    total_ok: int = 0                           # 成功数
    total_failed: int = 0                       # 失败数
    provider: str = ""                          # 使用的提供者
    meta: dict = {}                             # 元数据
```

### SearchResponse

```python
class SearchResponse(BaseModel):
    query: str                      # 搜索词
    source: SourceType              # 数据来源
    total_results: int | None       # 总结果数
    results: list[PaperResult] | list[PatentResult] | list[WebSearchResult]
    page: int = 1                   # 当前页
    per_page: int = 10              # 每页数量
```

### Author / Applicant

```python
class Author(BaseModel):
    name: str
    affiliation: str | None = None
    orcid: str | None = None

class Applicant(BaseModel):
    name: str
    country: str | None = None
```

## CLI 命令

### 搜索

```bash
# 论文搜索
souwen search paper <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 专利搜索
souwen search patent <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 网页搜索
souwen search web <query> [--engines/-e ENG1,ENG2] [--limit/-n 10] [--json/-j]
```

输出格式：
- 默认：Rich 表格（论文显示 Title/Year/Citations/DOI/Source）
- `--json`：JSON 格式（适合管道处理，如 `| jq '.[]'`）

### 配置

```bash
souwen config show    # 显示当前配置（API Key 脱敏）
souwen config init    # 生成 souwen.yaml 模板
```

### 数据源

```bash
souwen sources        # 列出所有数据源及其状态
```

### 健康检查

```bash
souwen doctor         # 检查所有数据源可用性
```

### 内容抓取

```bash
# 抓取网页内容（默认 builtin，零配置）
souwen fetch <urls...> [--provider/-p builtin] [--timeout/-t 30] [--json/-j]

# 示例
souwen fetch https://example.com                      # 内置抓取
souwen fetch https://a.com https://b.com -p jina_reader  # Jina Reader
souwen fetch https://example.com --json               # JSON 输出
```

### API 服务

```bash
souwen serve [--port 8000]   # 启动 FastAPI 服务
```

启动后可访问 OpenAPI 文档：`GET /docs`

## HTTP API（Server 模式）

### 认证：三角色系统

SouWen 支持三级角色认证（Guest/User/Admin），并向后兼容旧版密码配置：

| 角色 | Token 来源 | 可访问端点 |
|------|------------|-----------|
| Guest 游客 | 无 Token（需 `guest_enabled=true`） | 搜索（受限源、限速） |
| User 用户 | `user_password` / `visitor_password` / `api_password` | 搜索 + `/sources` + 只读管理 |
| Admin 管理员 | `admin_password` / `api_password` | 全部端点 |

**密码优先级：**

- 用户端点：`user_password` > `visitor_password` > `api_password` > 无（开放）
- 管理端点：`admin_password` > `api_password` > 无（开放）
- Admin Token 自动满足所有低级别端点（Admin ⊃ User ⊃ Guest）
- 显式将 `user_password` 或 `admin_password` 设为空字符串 `""` 表示**强制开放**该作用域

**请求格式：** `Authorization: Bearer <password>`

**角色自检：** `GET /api/v1/whoami` — 返回当前角色和可用功能列表，用于前端 UI 动态渲染。

> ⚠️ 当未设置任何密码时，所有端点（含管理端点）开放访问。生产部署务必至少设置 `admin_password`。
> 此外，可通过环境变量 `SOUWEN_ADMIN_OPEN=1` 显式声明"管理端开放"以避免启动告警。

### 错误响应格式

所有 4xx/5xx 错误统一为：

```json
{
  "error": "rate_limited",
  "detail": "请求过于频繁，每 60 秒最多 60 次",
  "request_id": "a1b2c3d4e5f6"
}
```

`error` 字段（机器可读错误码）映射：

| HTTP 状态码 | error 码 |
|-------------|----------|
| 400 | `bad_request` |
| 401 | `unauthorized` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 502 | `bad_gateway` |
| 503 | `service_unavailable` |
| 504 | `gateway_timeout` |
| 其他 | `error` |

### 速率限制

搜索端点（`/api/v1/search/*`）默认 **60 请求 / 60 秒 / IP**（基于内存滑动窗口）。
当配置了 `trusted_proxies`（CIDR 列表）时，会从受信代理转发的 `X-Forwarded-For` 提取真实 IP，否则使用 TCP 直连地址。

触发限流时返回 `429`，并附带以下响应头：

| 响应头 | 含义 |
|--------|------|
| `Retry-After` | 建议重试前等待的秒数 |
| `X-RateLimit-Limit` | 窗口内最大请求数 |
| `X-RateLimit-Remaining` | 窗口内剩余配额（429 时为 `0`） |
| `X-RateLimit-Reset` | 配额重置的 Unix 时间戳（秒） |

### 基础端点

#### `GET /health`

健康检查，无需认证。用于容器编排（K8s）存活探针。

**响应示例：**
```json
{ "status": "ok", "version": "0.6.3" }
```

> `version` 字段动态返回当前 `souwen.__version__`。

#### `GET /readiness`

K8s readiness 探针（v0.6.1 引入）。仅做本地检查（配置可加载 + 数据源注册表非空），不触发任何网络调用，避免探针超时。

**响应示例（就绪）：**
```json
{ "ready": true, "version": "0.6.3", "error": null }
```

**响应示例（503 未就绪）：**
```json
{ "ready": false, "version": "0.6.3", "error": "source registry is empty" }
```

#### `GET /` 与 `GET /panel`

- 当 `expose_docs=true`（默认）时，`GET /` 重定向到 `/docs`（Swagger UI）。
- 当 `expose_docs=false` 时，`GET /` 返回 JSON 元信息（`{name, version, panel, docs}`）。
- `GET /panel` 返回管理面板 HTML（不含在 OpenAPI schema 中）。

`/panel` 的 HTML 经内存缓存，并附带：

```
ETag: "<sha256-16hex>"
Cache-Control: public, max-age=3600
```

客户端在 `If-None-Match` 命中时返回 **304 Not Modified**（仅头部 `ETag`，无响应体）。支持 RFC 7232 通配符 `*` 和逗号分隔的 ETag 列表。

---

### 搜索端点 (`/api/v1/...`)

受 `check_search_auth` 与 `rate_limit_search` 双重保护。

#### `GET /api/v1/search/paper`

搜索学术论文（多源并联）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词 |
| `sources` | string | `"openalex,arxiv"` | 数据源列表，逗号分隔 |
| `per_page` | int (1-100) | `10` | 每个数据源返回结果数 |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504；`null` 表示无超时 |

**响应示例：**
```json
{
  "query": "transformer",
  "sources": ["openalex", "arxiv"],
  "results": [ ... ],
  "total": 20,
  "meta": {
    "requested": ["openalex", "arxiv"],
    "succeeded": ["openalex", "arxiv"],
    "failed": []
  }
}
```

**错误状态码：** `502 bad_gateway`（所有数据源均失败）、`504 gateway_timeout`（超过 `timeout`）。

#### `GET /api/v1/search/patent`

搜索专利。参数与 paper 一致，仅默认源不同：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词 |
| `sources` | string | `"google_patents"` | 数据源列表，逗号分隔 |
| `per_page` | int (1-100) | `10` | 每个数据源返回结果数 |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504 |

#### `GET /api/v1/search/web`

搜索网页（多引擎并联 + URL 去重）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 搜索关键词 |
| `engines` | string | `"duckduckgo,bing"` | 搜索引擎，逗号分隔 |
| `per_page` | int (1-50) | `10` | 每引擎最大结果数（**主名称**） |
| `max_results` | int (1-50) \| null | `null` | 兼容旧版的别名；显式提供时**优先级高于 `per_page`** |
| `timeout` | float (1-300) \| null | `null` | 端点硬超时（秒），超时返回 504 |

> 兼容性提示：旧客户端可继续使用 `max_results`；新客户端推荐 `per_page`。

#### `GET /api/v1/sources`

列出所有可用数据源及其状态（受访客认证保护）。

**响应示例：**
```json
{
  "paper": [
    { "name": "openalex", "needs_key": false, "description": "OpenAlex 开放学术图谱" }
  ],
  "patent": [ ... ],
  "web": [ ... ]
}
```

---

### 管理端点 (`/api/v1/admin/...`)

> 管理端点由 `require_auth` 强制保护，验证 `effective_admin_password`（`admin_password` > `api_password`）。
> 未设置任一密码时管理端点开放访问，建议生产环境至少设置 `admin_password`。

#### `GET /api/v1/admin/config`

查看当前配置。敏感字段（包含 `key`/`secret`/`token`/`password` 的字段）自动脱敏为 `"***"`。

**响应示例：**
```json
{
  "api_password": "***",
  "semantic_scholar_key": "***",
  "rate_limit_per_minute": 30,
  ...
}
```

#### `POST /api/v1/admin/config/reload`

重新加载配置（从 YAML 和环境变量）。

**响应示例：**
```json
{ "status": "ok", "password_set": true }
```

#### `GET /api/v1/admin/doctor`

数据源健康检查，返回配置状态和已知限制提示；当前不执行实时连通性探测。

**响应示例：**
```json
{
  "total": 37,
  "ok": 24,
  "sources": [
    {
      "name": "openalex",
      "category": "paper",
      "status": "ok",
      "integration_type": "open_api",
      "required_key": "openalex_email",
      "message": "可免配置使用；设置 openalex_email 可帮助礼貌访问"
    },
    {
      "name": "semantic_scholar",
      "category": "paper",
      "status": "limited",
      "integration_type": "official_api",
      "required_key": "semantic_scholar_api_key",
      "message": "免 Key 模式易限流，建议设置 semantic_scholar_api_key"
    }
  ]
}
```

#### `GET /api/v1/admin/warp`

获取 WARP 代理当前状态。

**响应示例：**
```json
{
  "status": "enabled",
  "mode": "wireproxy",
  "owner": "shell",
  "socks_port": 1080,
  "http_port": 0,
  "ip": "104.28.x.x",
  "pid": 12345,
  "protocol": "wireguard",
  "proxy_type": "socks5"
}
```

#### `GET /api/v1/admin/warp/modes`

列出所有 WARP 模式的可用性、协议、代理类型和部署要求。

**模式：** `wireproxy` / `kernel` / `usque` / `warp-cli` / `external`

**响应示例：**
```json
{
  "modes": [
    {
      "id": "usque",
      "name": "usque (MASQUE/QUIC)",
      "protocol": "masque",
      "installed": true,
      "requires_privilege": false,
      "docker_only": false,
      "proxy_types": ["socks5", "http"],
      "description": "MASQUE/QUIC 协议，现代化方案，支持 SOCKS5 和 HTTP 代理"
    }
  ]
}
```

#### `POST /api/v1/admin/warp/enable`

启用 Cloudflare WARP 代理。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mode` | string | `"auto"` | 模式: `auto` / `wireproxy` / `kernel` / `usque` / `warp-cli` / `external` |
| `socks_port` | int (1-65535) | `1080` | SOCKS5 端口 |
| `http_port` | int (0-65535) | `0` | HTTP 代理端口（`0` 表示不启用；适用于 `usque` 等支持 HTTP 代理的模式） |
| `endpoint` | string \| null | `null` | 自定义 WARP Endpoint |

**响应示例：**
```json
{ "ok": true, "mode": "wireproxy", "ip": "104.28.x.x" }
```

**错误响应 (400)：**
```json
{ "detail": "wireproxy binary not found" }
```

#### `POST /api/v1/admin/warp/register`

注册新的 Cloudflare WARP 账号。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `backend` | string | `"wgcf"` | 注册后端：`wgcf`（WireGuard 配置）/ `usque`（MASQUE 配置） |

**响应示例：**
```json
{ "ok": true, "backend": "wgcf", "config_path": ".../wgcf-raw.conf" }
```

#### `POST /api/v1/admin/warp/test`

测试当前 WARP 代理连接，返回出口 IP、端口、模式与协议。

**响应示例：**
```json
{
  "ok": true,
  "ip": "104.28.x.x",
  "port": 1080,
  "mode": "usque",
  "protocol": "masque",
  "proxy_type": "both"
}
```

#### `GET /api/v1/admin/warp/config`

获取当前 WARP 相关配置项；`warp_license_key` 和 `warp_team_token` 仅返回是否已配置，代理 URL 中的用户名和密码会被掩码。

**响应示例：**
```json
{
  "warp_enabled": false,
  "warp_mode": "auto",
  "warp_socks_port": 1080,
  "warp_http_port": 0,
  "warp_endpoint": null,
  "warp_external_proxy": null,
  "warp_usque_path": null,
  "warp_usque_config": null,
  "warp_gost_args": null,
  "has_license_key": false,
  "has_team_token": false
}
```

#### `POST /api/v1/admin/warp/disable`

禁用 WARP 代理。

**响应示例：**
```json
{ "ok": true }
```

---

### 内容抓取端点 (`/api/v1/fetch`)

受 `require_auth`（管理密码）与 `rate_limit_search` 双重保护。

#### `POST /api/v1/fetch`

抓取网页内容，支持 19 个提供者。

**请求体 (JSON)：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | `list[str]` (1-20) | *(必填)* | 目标 URL 列表 |
| `provider` | `string` | `"builtin"` | 提供者: `builtin` / `jina_reader` / `tavily` / `firecrawl` / `exa` / `crawl4ai` / `scrapfly` / `diffbot` / `scrapingbee` / `zenrows` / `scraperapi` / `apify` / `cloudflare` / `wayback` / `newspaper` / `readability` / `mcp` / `site_crawler` / `deepwiki` |
| `timeout` | `float` (1-120) | `30` | 每 URL 超时秒数 |

**请求示例：**
```json
{
  "urls": ["https://example.com/article"],
  "provider": "builtin",
  "timeout": 30
}
```

**响应示例：**
```json
{
  "urls": ["https://example.com/article"],
  "results": [
    {
      "url": "https://example.com/article",
      "final_url": "https://example.com/article",
      "title": "示例文章",
      "content": "# 示例文章\n\n正文内容...",
      "content_format": "markdown",
      "source": "builtin",
      "snippet": "正文内容...",
      "published_date": "2024-01-01",
      "author": "作者",
      "error": null,
      "raw": {}
    }
  ],
  "total": 1,
  "total_ok": 1,
  "total_failed": 0,
  "provider": "builtin",
  "meta": {}
}
```

**错误状态码：** `400`（无效提供者）、`504`（超时）

**安全特性：**
- SSRF 防护：DNS 解析 + 私有/保留 IP 拦截
- 重定向安全：每一跳校验目标 IP，防止多跳 SSRF 攻击
- 管理密码认证：需要 `admin_password`（或回退 `api_password`）

## MCP 工具

SouWen 支持 [Model Context Protocol](https://modelcontextprotocol.io/)，可作为 AI Agent 的工具服务。

### 启动

```bash
python -m souwen.integrations.mcp_server
```

需安装 `pip install mcp`。

### 工具列表

#### `search_papers`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | array | `["openalex", "arxiv", "crossref"]` | 数据源 |
| `limit` | int | `5` | 每源返回数量 |

返回：JSON `SearchResponse` 数组

#### `search_patents`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | array | `["google_patents"]` | 数据源 |
| `limit` | int | `5` | 结果数 |

返回：JSON `SearchResponse` 数组

#### `web_search`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `engines` | array | `null`（由后端默认 `["duckduckgo", "bing"]` 决定） | 引擎列表 |
| `limit` | int | `10` | 每引擎最大结果数 |

返回：JSON `SearchResponse` 对象

#### `get_status`

无参数。返回所有数据源的健康状态报告。

#### `fetch_content`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `urls` | array | — | 待抓取的 URL 列表 |
| `provider` | string | `"builtin"` | 内容提取提供者，默认 `builtin`（零配置）。可选：`jina_reader` / `tavily` / `firecrawl` / `exa` / `crawl4ai` / `scrapfly` / `diffbot` / `scrapingbee` / `zenrows` / `scraperapi` / `apify` / `cloudflare` / `wayback` / `newspaper` / `readability` / `mcp` / `site_crawler` / `deepwiki` |

返回：JSON `FetchResponse` 对象（含 `results`、`total`、`total_ok`、`total_failed`）。

> 共 5 个 MCP 工具：`search_papers`、`search_patents`、`web_search`、`get_status`、`fetch_content`（PR #23）。

---

## 多媒体与扩展端点（V1 新增）

下列端点在 V1 中陆续随领域子包接入，统一受 `check_search_auth` + `rate_limit_search` 保护。

### 图片 / 视频（DuckDuckGo）

#### `GET /api/v1/search/images`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `q` | string (1-500) | *(必填)* | 关键词 |
| `max_results` | int (1-100) | `20` | 最大结果数 |
| `region` | string | `wt-wt` | 区域（`wt-wt`=全球，`cn-zh`=中国） |
| `safesearch` | string | `moderate` | `on` / `moderate` / `off` |
| `timeout` | float (1-120) \| null | `null` | 端点硬超时秒数 |

#### `GET /api/v1/search/videos`

参数同 `/search/images`，返回 `title / duration / publisher / thumbnail / embed_url` 等字段。

### YouTube Data API

需配置 `youtube_api_key`，缺失时返回 `503`。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/youtube/trending` | `region`, `category`, `max_results` | 按地区/分类拉取热门视频 |
| `GET /api/v1/youtube/video/{video_id}` | — | 视频详情（含播放/点赞/评论统计） |
| `GET /api/v1/youtube/transcript/{video_id}` | `lang` | 提取字幕（**零配额**，页面抓取方式） |

### Wayback Machine（archive 域）

| 端点 | 认证 | 主要参数 | 说明 |
|------|------|----------|------|
| `GET /api/v1/wayback/cdx` | 访客 | `url`, `from`, `to`, `limit`, `filter_status`, `collapse` | URL 历史快照列表 |
| `GET /api/v1/wayback/check` | 访客 | `url`, `timestamp` | 快照可用性查询 |
| `POST /api/v1/admin/wayback/save` | 管理 | `url`, `timeout` | 触发即时存档（IA 全局速率约 15 次/分钟） |

### 链接与 sitemap 工具（fetch 域）

需要管理密码（含 SSRF 风险）。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/links` | `url`, `base_url`, `limit` (1-1000) | 提取页面 `<a href>` 链接，去重 + SSRF 过滤 |
| `GET /api/v1/sitemap` | `url`, `discover`, `limit` (1-50000) | 解析 sitemap.xml / sitemap index / gzip；`discover=true` 时从 robots.txt 自动发现 |

### Bilibili（video / social 域）

`prefix=/api/v1/bilibili`，受访客认证保护。错误码映射：`BilibiliNotFound→404`、`BilibiliAuthRequired→401`、`BilibiliRateLimited→429`、`BilibiliRiskControl→403`、`BilibiliError→502`。

| 端点 | 主要参数 | 说明 |
|------|----------|------|
| `GET /api/v1/bilibili/video/{bvid}` | — | 视频详情（标题、UP、统计、标签） |
| `GET /api/v1/bilibili/search` | `keyword`, `max_results` (1-50), `order` | 视频搜索（`order` ∈ totalrank/click/pubdate/dm/stow） |
| `GET /api/v1/bilibili/search/users` | `keyword`, `page`, `max_results` | 用户搜索 |
| `GET /api/v1/bilibili/search/articles` | `keyword`, `page`, `max_results` | 专栏文章搜索 |

### 数据源频道配置（V1 admin）

| 端点 | 说明 |
|------|------|
| `GET /api/v1/admin/sources/config` | 列出所有源的频道配置（`enabled / proxy / http_backend / base_url / has_api_key / headers / params / category / integration_type`） |
| `GET /api/v1/admin/sources/config/{source_name}` | 单源频道配置（404 未知源） |
| `PUT /api/v1/admin/sources/config/{source_name}` | JSON 体更新单源运行时配置（避免 Key 入日志），重启不持久化 |
| `GET /api/v1/admin/proxy` / `PUT` | 全局 `proxy` 与 `proxy_pool` 读写（含 SOCKS 依赖检查） |
| `GET /api/v1/admin/http-backend` / `PUT` | HTTP 后端总览与按源覆盖（`auto`/`curl_cffi`/`httpx`） |

请求体示例（`PUT /api/v1/admin/sources/config/duckduckgo`）：

```json
{
  "enabled": true,
  "proxy": "warp",
  "http_backend": "curl_cffi"
}
```

> 完整字段语义见 [configuration.md](./configuration.md#数据源频道配置sources)。
