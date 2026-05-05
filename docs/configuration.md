# 配置详解

> SouWen 配置系统：从零配置到完全自定义

> **V2 架构提示**：所有配置项均集中在 `src/souwen/config/models.py` 的 `SouWenConfig`（Pydantic 模型）。新增数据源时若需要凭据，需要在 `SouWenConfig` 加字段，并在 `registry/sources/` 的 `SourceAdapter` 里通过 `config_field` / `credential_fields` 引用。详见 [adding-a-source.md](./adding-a-source.md)。

## 配置优先级

从高到低：

1. **环境变量** — `SOUWEN_<FIELD_NAME>`（如 `SOUWEN_OPENALEX_EMAIL`）
2. **项目 YAML** — `./souwen.yaml`（当前目录）
3. **用户 YAML** — `~/.config/souwen/config.yaml`
4. **.env 文件** — `./`（通过 python-dotenv 加载）
5. **内置默认值** — None 或空

## 快速开始

```bash
# 生成配置模板
souwen config init

# 查看当前配置（API Key 脱敏显示）
souwen config show
```

也可以复制 `.env.example` 为 `.env` 后按需填写：

```bash
cp .env.example .env
```

## YAML 配置格式

参考 `souwen.example.yaml`：

```yaml
paper:
  openalex_email: your@email.com
  semantic_scholar_api_key: your_key
  core_api_key: your_key
  pubmed_api_key: your_key
  unpaywall_email: your@email.com
  ieee_api_key: your_key

patent:
  epo_consumer_key: your_key
  epo_consumer_secret: your_secret
  cnipa_client_id: your_id
  cnipa_client_secret: your_secret
  uspto_api_key: your_key
  lens_api_token: your_token
  patsnap_api_key: your_key

web:
  searxng_url: http://localhost:8888
  tavily_api_key: your_key
  exa_api_key: your_key
  serper_api_key: your_key
  brave_api_key: your_key
  serpapi_api_key: your_key
  firecrawl_api_key: your_key
  jina_api_key: your_key             # Jina Reader（可选，免费层无需 Key）
  scrapfly_api_key: your_key         # Scrapfly（JS 渲染+AI 提取）
  diffbot_api_token: your_token      # Diffbot（结构化内容提取）
  scrapingbee_api_key: your_key      # ScrapingBee（代理+JS 渲染+反爬）
  zenrows_api_key: your_key          # ZenRows（代理+JS 渲染+反爬）
  scraperapi_api_key: your_key       # ScraperAPI（代理池+JS 渲染）
  apify_api_token: your_token        # Apify（平台化 Actor 爬虫）
  cloudflare_api_token: your_token  # Cloudflare Browser Rendering
  cloudflare_account_id: your_id    # Cloudflare 账户 ID
  feishu_app_id: your_app_id        # 飞书云文档搜索（PR #7）
  feishu_app_secret: your_app_secret
  zhipuai_api_key: your_key         # 智谱 AI Web Search Pro（PR #12）
  aliyun_iqs_api_key: your_key      # 阿里云 IQS 通义晓搜（PR #13）
  metaso_api_key: your_key          # Metaso（秘塔）搜索
  perplexity_api_key: your_key
  linkup_api_key: your_key
  xcrawl_api_key: your_key
  scrapingdog_api_key: your_key
  whoogle_url: http://localhost:5000
  websurfx_url: http://localhost:8080
  github_token: ghp_your_token
  stackoverflow_api_key: your_key
  youtube_api_key: your_key

general:
  proxy: http://proxy:7890
  proxy_pool:
    - http://proxy1:7890
    - http://proxy2:7890
    - socks5://proxy3:1080
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen
  default_http_backend: auto
  http_backend: {}

server:
  api_password: ~              # 旧版统一密码（向后兼容）
  visitor_password: ~          # 访客密码（仅保护搜索端点，优先于 api_password）
  admin_password: ~            # 管理密码（仅保护管理端点，优先于 api_password）
  cors_origins: []
  trusted_proxies:             # 反向代理 IP/CIDR 名单
    - 10.0.0.0/8
    - 127.0.0.1
  expose_docs: true            # 是否暴露 /docs、/redoc、/openapi.json

warp:
  warp_enabled: false
  warp_mode: auto
  warp_socks_port: 1080
  warp_http_port: 0
  warp_endpoint: ~
  warp_external_proxy: ~

sources: {}
```

## 全部配置字段

### 论文 API

| 字段 | 环境变量 | 必需 | 说明 |
|------|---------|------|------|
| `openalex_email` | `SOUWEN_OPENALEX_EMAIL` | 推荐 | 进入 polite pool，获得更快响应 |
| `semantic_scholar_api_key` | `SOUWEN_SEMANTIC_SCHOLAR_API_KEY` | 可选 | 提高速率限制 |
| `core_api_key` | `SOUWEN_CORE_API_KEY` | CORE 必需 | 申请：https://core.ac.uk/services/api |
| `pubmed_api_key` | `SOUWEN_PUBMED_API_KEY` | 可选 | 提高速率限制 |
| `unpaywall_email` | `SOUWEN_UNPAYWALL_EMAIL` | Unpaywall 必需 | 作为请求标识 |
| `ieee_api_key` | `SOUWEN_IEEE_API_KEY` | IEEE Xplore 必需 | IEEE Xplore API Key |

### 专利 API

| 字段 | 环境变量 | 必需 | 说明 |
|------|---------|------|------|
| `epo_consumer_key` | `SOUWEN_EPO_CONSUMER_KEY` | EPO 必需 | EPO OPS Consumer Key |
| `epo_consumer_secret` | `SOUWEN_EPO_CONSUMER_SECRET` | EPO 必需 | EPO OPS Consumer Secret |
| `cnipa_client_id` | `SOUWEN_CNIPA_CLIENT_ID` | CNIPA 必需 | CNIPA OAuth Client ID |
| `cnipa_client_secret` | `SOUWEN_CNIPA_CLIENT_SECRET` | CNIPA 必需 | CNIPA OAuth Secret |
| `uspto_api_key` | `SOUWEN_USPTO_API_KEY` | USPTO ODP 必需 | USPTO 官方数据门户 |
| `lens_api_token` | `SOUWEN_LENS_API_TOKEN` | The Lens 必需 | Bearer Token |
| `patsnap_api_key` | `SOUWEN_PATSNAP_API_KEY` | PatSnap 必需 | 智慧芽 API Key |

### 搜索引擎 API

| 字段 | 环境变量 | 必需 | 说明 |
|------|---------|------|------|
| `searxng_url` | `SOUWEN_SEARXNG_URL` | SearXNG 必需 | 自建实例 URL |
| `tavily_api_key` | `SOUWEN_TAVILY_API_KEY` | Tavily 必需 | AI 搜索 API |
| `exa_api_key` | `SOUWEN_EXA_API_KEY` | Exa 必需 | 语义搜索 API |
| `serper_api_key` | `SOUWEN_SERPER_API_KEY` | Serper 必需 | Google SERP API |
| `brave_api_key` | `SOUWEN_BRAVE_API_KEY` | Brave API 必需 | 官方 REST API |
| `serpapi_api_key` | `SOUWEN_SERPAPI_API_KEY` | SerpAPI 必需 | 多引擎 SERP |
| `firecrawl_api_key` | `SOUWEN_FIRECRAWL_API_KEY` | Firecrawl 必需 | 网页爬取 API |
| `perplexity_api_key` | `SOUWEN_PERPLEXITY_API_KEY` | Perplexity 必需 | AI 搜索 API |
| `linkup_api_key` | `SOUWEN_LINKUP_API_KEY` | Linkup 必需 | 聚合搜索 API |
| `xcrawl_api_key` | `SOUWEN_XCRAWL_API_KEY` | XCrawl 必需 | 搜索+抓取 API |
| `scrapingdog_api_key` | `SOUWEN_SCRAPINGDOG_API_KEY` | ScrapingDog 必需 | SERP 代理 |
| `whoogle_url` | `SOUWEN_WHOOGLE_URL` | Whoogle 必需 | 自建实例 URL |
| `websurfx_url` | `SOUWEN_WEBSURFX_URL` | Websurfx 必需 | 自建实例 URL |
| `github_token` | `SOUWEN_GITHUB_TOKEN` | 可选 | GitHub Personal Access Token（提升速率限制） |
| `stackoverflow_api_key` | `SOUWEN_STACKOVERFLOW_API_KEY` | 可选 | StackOverflow API Key（提升配额） |
| `youtube_api_key` | `SOUWEN_YOUTUBE_API_KEY` | YouTube 必需 | YouTube Data API v3 Key |
| `jina_api_key` | `SOUWEN_JINA_API_KEY` | 可选 | Jina Reader 网页抓取（免费层无需 Key） |
| `scrapfly_api_key` | `SOUWEN_SCRAPFLY_API_KEY` | Scrapfly 必需 | JS 渲染+AI 提取+反爬绕过 |
| `diffbot_api_token` | `SOUWEN_DIFFBOT_API_TOKEN` | Diffbot 必需 | 结构化内容提取（文章/学术） |
| `scrapingbee_api_key` | `SOUWEN_SCRAPINGBEE_API_KEY` | ScrapingBee 必需 | 代理池+JS 渲染+反爬绕过 |
| `zenrows_api_key` | `SOUWEN_ZENROWS_API_KEY` | ZenRows 必需 | 代理池+JS 渲染+自动解析 |
| `scraperapi_api_key` | `SOUWEN_SCRAPERAPI_API_KEY` | ScraperAPI 必需 | 大规模代理池+JS 渲染 |
| `apify_api_token` | `SOUWEN_APIFY_API_TOKEN` | Apify 必需 | 平台化 Actor 爬虫 |
| `cloudflare_api_token` | `SOUWEN_CLOUDFLARE_API_TOKEN` | Cloudflare 必需 | Browser Rendering API Token |
| `cloudflare_account_id` | `SOUWEN_CLOUDFLARE_ACCOUNT_ID` | Cloudflare 必需 | Cloudflare 账户 ID |
| `feishu_app_id` | `SOUWEN_FEISHU_APP_ID` | 飞书云文档必需 | 飞书 / Lark 自建应用 App ID（PR #7） |
| `feishu_app_secret` | `SOUWEN_FEISHU_APP_SECRET` | 飞书云文档必需 | 飞书 / Lark 自建应用 App Secret |
| `zhipuai_api_key` | `SOUWEN_ZHIPUAI_API_KEY` | 智谱 AI 必需 | Web Search Pro API Key（含 AI 摘要，PR #12） |
| `aliyun_iqs_api_key` | `SOUWEN_ALIYUN_IQS_API_KEY` | 阿里云 IQS 必需 | 通义晓搜 API Key（含 AI 摘要，PR #13） |
| `metaso_api_key` | `SOUWEN_METASO_API_KEY` | Metaso 必需 | 秘塔搜索 API Key（文档/网页/学术） |

### 社交 / 视频 / 办公 / 个人库

| 字段 | 环境变量 | 必需 | 说明 |
|------|---------|------|------|
| `bilibili_sessdata` | `SOUWEN_BILIBILI_SESSDATA` | 可选 | Bilibili SESSDATA Cookie（启用授权 API：高画质 / 字幕 / 高频） |
| `twitter_bearer_token` | `SOUWEN_TWITTER_BEARER_TOKEN` | Twitter 必需 | X API v2 Bearer Token（Basic 套餐及以上） |
| `reddit_client_id` | `SOUWEN_REDDIT_CLIENT_ID` | Reddit 必需 | OAuth2 App Client ID |
| `reddit_client_secret` | `SOUWEN_REDDIT_CLIENT_SECRET` | Reddit 必需 | OAuth2 App Client Secret |
| `facebook_app_id` / `facebook_app_secret` | `SOUWEN_FACEBOOK_APP_*` | Facebook 必需 | Meta 应用凭证 |
| `zotero_api_key` | `SOUWEN_ZOTERO_API_KEY` | Zotero 必需 | Zotero Web API Key |
| `zotero_library_id` | `SOUWEN_ZOTERO_LIBRARY_ID` | Zotero 必需 | 用户 ID 或群组 ID |
| `zotero_library_type` | `SOUWEN_ZOTERO_LIBRARY_TYPE` | 可选 | `user`（默认）或 `group` |

### MCP（Model Context Protocol）

| 字段 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `mcp_server_url` | `SOUWEN_MCP_SERVER_URL` | None | 远端 MCP Server 端点（启用 fetch provider=mcp 时必需） |
| `mcp_transport` | `SOUWEN_MCP_TRANSPORT` | `streamable_http` | `streamable_http` 或 `sse` |
| `mcp_fetch_tool_name` | `SOUWEN_MCP_FETCH_TOOL_NAME` | `fetch` | 远端 MCP fetch 工具名 |
| `mcp_extra_headers` | `SOUWEN_MCP_EXTRA_HEADERS` | `{}` | JSON 对象，附加给 MCP 请求 |

### 网络设置

| 字段 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `proxy` | `SOUWEN_PROXY` | None | 单个代理 URL |
| `proxy_pool` | `SOUWEN_PROXY_POOL` | `[]` | 多代理 URL 列表，随机选取（逗号分隔） |
| `timeout` | `SOUWEN_TIMEOUT` | `30` | 请求超时秒数 |
| `max_retries` | `SOUWEN_MAX_RETRIES` | `3` | 最大重试次数 |
| `data_dir` | `SOUWEN_DATA_DIR` | `~/.local/share/souwen` | 数据存储目录 |
| `default_http_backend` | `SOUWEN_DEFAULT_HTTP_BACKEND` | `"auto"` | 全局 HTTP 后端：auto &#124; curl_cffi &#124; httpx |
| `http_backend` | `SOUWEN_HTTP_BACKEND` | `{}` | 按源覆盖 HTTP 后端（JSON 对象） |
| — | `SOUWEN_MAX_CONCURRENCY` | `10` | 聚合搜索并发上限（v0.6.0，仅环境变量） |

### 服务端

| 字段 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `api_password` | `SOUWEN_API_PASSWORD` | None | 旧版统一密码（向后兼容，同时作用于用户 + 管理） |
| `user_password` | `SOUWEN_USER_PASSWORD` | None | 用户密码，保护搜索和 `/sources` |
| `admin_password` | `SOUWEN_ADMIN_PASSWORD` | None | 管理密码，保护全部 `/api/v1/admin/*` |
| `guest_enabled` | `SOUWEN_GUEST_ENABLED` | `false` | 是否启用游客访问（无 Token 也可搜索，受限源） |
| `cors_origins` | `SOUWEN_CORS_ORIGINS` | `[]` | CORS 允许来源列表（逗号分隔），为空时不启用 CORS |
| `trusted_proxies` | `SOUWEN_TRUSTED_PROXIES` | `[]` | 受信反向代理 IP/CIDR 列表，逗号分隔 |
| `expose_docs` | `SOUWEN_EXPOSE_DOCS` | `true` | 是否暴露 `/docs`、`/redoc`、`/openapi.json` |

> 旧版 `visitor_password`（`SOUWEN_VISITOR_PASSWORD`）仍可使用，会自动映射为 `user_password`。

**三角色认证模型**：

| 角色 | 获取方式 | 可用端点 |
|------|----------|----------|
| Guest 游客 | 无 Token（需 `guest_enabled=true`） | 搜索（受限源、限速） |
| User 用户 | `user_password` / `visitor_password` / `api_password` | 搜索 + `/sources` |
| Admin 管理员 | `admin_password` / `api_password` | 全部权限 |

**密码优先级**：

- 用户端点：`user_password` > `visitor_password` > `api_password` > 无（开放）
- 管理端点：`admin_password` > `api_password` > 无（默认锁定，需 `SOUWEN_ADMIN_OPEN=1` 显式放行）
- Admin Token 自动满足 User/Guest 端点（角色层级：Admin ⊃ User ⊃ Guest）

显式将 `user_password` 设为空字符串可开放用户端点；显式将 `admin_password` 设为空字符串只表示忽略 `api_password` 回退，管理端仍需 `SOUWEN_ADMIN_OPEN=1` 才开放。

## 代理池配置

支持多代理 URL 随机轮换，降低单 IP 被封风险：

```yaml
general:
  proxy_pool:
    - http://proxy1:7890
    - http://proxy2:7890
    - socks5://proxy3:1080
```

`get_proxy()` 方法优先从 `proxy_pool` 随机选取，为空时回退到 `proxy`。

## 编程方式获取配置

```python
from souwen import get_config, reload_config

# 获取全局配置单例
config = get_config()
print(config.timeout)
print(config.get_proxy())

# 重新加载配置（修改环境变量后）
config = reload_config()
```

## 服务端安全

### Admin API 默认锁定 (P0-7)

当 `admin_password`（或回退的 `api_password`）**未设置**时，所有 `/api/v1/admin/*` 端点默认返回 `401 Unauthorized`，响应体包含提示信息。推荐的使用方式：

| 场景 | 做法 |
| --- | --- |
| 生产部署 | 设置 `SOUWEN_ADMIN_PASSWORD=<强随机串>`，使用 `Authorization: Bearer <password>` 访问 |
| 本地开发 / CI 冒烟测试 | 可选 `SOUWEN_ADMIN_OPEN=1` 显式绕过锁定（启动时会打 WARNING 日志） |

未配置密码且未设置 `SOUWEN_ADMIN_OPEN` 时，任何 admin 请求都会被拒绝——默认最安全。

### 反向代理感知的客户端 IP (P0-8)

速率限制、审计日志等模块需要真实客户端 IP。SouWen 只在请求的直连来源位于 `trusted_proxies` 名单时，才从 `X-Forwarded-For` 取最左侧 IP，否则直接使用 TCP 对端地址，避免攻击者通过伪造 XFF 绕过限流。

配置示例：

```yaml
server:
  trusted_proxies:
    - 10.0.0.0/8
    - 172.16.0.0/12
    - 127.0.0.1
```

也可通过 `SOUWEN_TRUSTED_PROXIES="10.0.0.0/8,127.0.0.1"` 环境变量设置。

### 文档开关 (P2-8)

默认暴露 `/docs`、`/redoc`、`/openapi.json`，方便开发联调。生产环境可关闭：

```yaml
server:
  expose_docs: false
```

关闭后这些路径会返回 404，`/health`、`/api/v1/*` 不受影响。

### WARP 代理

| 字段 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `warp_enabled` | `SOUWEN_WARP_ENABLED` / `WARP_ENABLED` | `false` | 是否启用内嵌 WARP 代理 |
| `warp_mode` | `SOUWEN_WARP_MODE` / `WARP_MODE` | `"auto"` | 模式：auto &#124; wireproxy &#124; kernel &#124; usque &#124; warp-cli &#124; external |
| `warp_socks_port` | `SOUWEN_WARP_SOCKS_PORT` / `WARP_SOCKS_PORT` | `1080` | SOCKS5 代理监听端口 |
| `warp_http_port` | `SOUWEN_WARP_HTTP_PORT` / `WARP_HTTP_PORT` | `0` | HTTP 代理监听端口；`0` 表示不启用，适用于 `usque` / `warp-cli` |
| `warp_endpoint` | `SOUWEN_WARP_ENDPOINT` / `WARP_ENDPOINT` | None | 自定义 Endpoint（如 `162.159.192.1:4500`） |
| `warp_usque_config` | `SOUWEN_WARP_USQUE_CONFIG` / `WARP_USQUE_CONFIG` | None | `usque` 模式的 config.json 路径 |
| `warp_external_proxy` | `SOUWEN_WARP_EXTERNAL_PROXY` / `WARP_EXTERNAL_PROXY` | None | `external` 模式使用的外部代理地址 |

> WARP 字段支持不带 `SOUWEN_` 前缀的环境变量（Docker entrypoint 兼容）。

### 数据源频道配置（sources）

按源名称覆盖全局默认值。所有字段可选，只需覆盖想要自定义的部分。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用此数据源 |
| `proxy` | string | `"inherit"` | 代理策略：inherit &#124; none &#124; warp &#124; 显式 URL |
| `http_backend` | string | `"auto"` | HTTP 后端：auto &#124; curl_cffi &#124; httpx |
| `base_url` | string | None | 覆盖数据源的基础 URL |
| `api_key` | string | None | 覆盖主 API Key（优先于全局 flat key；多字段凭据的其他字段仍读取全局 flat 配置） |
| `headers` | object | `{}` | 附加请求头 |
| `params` | object | `{}` | 附加参数（传递给搜索方法；值仅支持字符串/数字/布尔值） |

环境变量：`SOUWEN_SOURCES='{"duckduckgo":{"proxy":"warp"}}'`（JSON 格式）

自建实例源（如 `searxng` / `whoogle` / `websurfx`）优先使用 `sources.<name>.base_url`；旧版 `sources.<name>.api_key` 与 flat `<name>_url` 仍作为兼容入口。数据源字段和运行时可见性规则见 [data-sources.md](./data-sources.md) 与 [api-reference.md](./api-reference.md#数据源频道配置admin)。

示例：

```yaml
sources:
  duckduckgo:
    enabled: true
    proxy: warp
    http_backend: curl_cffi
  tavily:
    api_key: tvly-xxxx
    params:
      search_depth: advanced
  scrapling:
    params:
      mode: fetcher        # fetcher / dynamic / stealthy
      content_format: text # text / html
  google_patents:
    enabled: false
```

`sources.scrapling.params` 只暴露可由 YAML 表达的 primitive 选项。`cookies`、`blocked_domains`、`page_setup` / `page_action` 等结构化或函数参数不作为配置入口；浏览器模式的 SSRF 请求拦截由 SouWen 内部注入。

## Docker 专用环境变量

容器入口脚本（`entrypoint.sh` + `scripts/warp-init.sh`）会在 SouWen 启动前生效，因此 WARP 系列变量同时支持**不带** `SOUWEN_` 前缀：

| 环境变量 | 等价 YAML 字段 | 说明 |
|----------|---------------|------|
| `WARP_ENABLED` | `warp.warp_enabled` | `1`/`true` 启用 WARP |
| `WARP_MODE` | `warp.warp_mode` | `auto` / `wireproxy` / `kernel` / `usque` / `warp-cli` / `external` |
| `WARP_SOCKS_PORT` | `warp.warp_socks_port` | SOCKS5 监听端口（默认 1080） |
| `WARP_HTTP_PORT` | `warp.warp_http_port` | HTTP 代理监听端口（`usque` / `warp-cli` 模式可用，默认 0 表示关闭） |
| `WARP_ENDPOINT` | `warp.warp_endpoint` | 自定义 WARP Endpoint（如 `162.159.192.1:4500`） |
| `WARP_USQUE_CONFIG` | `warp.warp_usque_config` | `usque` 模式的 config.json 路径 |
| `WARP_EXTERNAL_PROXY` | `warp.warp_external_proxy` | `external` 模式使用的外部代理地址 |
| `WARP_CONFIG_B64` | — | Base64 编码的 wireproxy / WireGuard 完整配置（仅 entrypoint 使用） |
| `GH_PROXY` | — | GitHub 下载加速前缀（用于 wgcf / wireproxy 二进制下载） |
| `SOUWEN_ADMIN_OPEN` | — | 管理端"显式开放"开关，未设管理密码时避免启动告警 |

> 详细 WARP 部署与五模式选择见 [warp-solutions.md](./warp-solutions.md)，反爬和代理使用建议见 [anti-scraping.md](./anti-scraping.md#warp-cloudflare-代理)。

## 配置相关交叉引用

- 添加新数据源（含 `config_field` 配置）：[adding-a-source.md](./adding-a-source.md)
- WARP 与代理细节：[anti-scraping.md](./anti-scraping.md)
- 服务端认证 / 管理端口 / 速率限制：[api-reference.md](./api-reference.md#http-apiserver-模式)
