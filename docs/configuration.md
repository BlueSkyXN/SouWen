# 配置详解

> SouWen 配置系统：从零配置到完全自定义

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
  perplexity_api_key: your_key
  linkup_api_key: your_key
  scrapingdog_api_key: your_key
  whoogle_url: http://localhost:5000
  websurfx_url: http://localhost:8080

general:
  proxy: http://proxy:7890
  proxy_pool:
    - http://proxy1:7890
    - http://proxy2:7890
    - socks5://proxy3:1080
  timeout: 30
  max_retries: 3
  data_dir: ~/.local/share/souwen
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
| `scrapingdog_api_key` | `SOUWEN_SCRAPINGDOG_API_KEY` | ScrapingDog 必需 | SERP 代理 |
| `whoogle_url` | `SOUWEN_WHOOGLE_URL` | Whoogle 必需 | 自建实例 URL |
| `websurfx_url` | `SOUWEN_WEBSURFX_URL` | Websurfx 必需 | 自建实例 URL |

### 网络设置

| 字段 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `proxy` | `SOUWEN_PROXY` | None | 单个代理 URL |
| `proxy_pool` | — | `[]` | 多代理 URL 列表，随机选取 |
| `timeout` | `SOUWEN_TIMEOUT` | `30` | 请求超时秒数 |
| `max_retries` | `SOUWEN_MAX_RETRIES` | `3` | 最大重试次数 |
| `data_dir` | `SOUWEN_DATA_DIR` | `~/.local/share/souwen` | 数据存储目录 |

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

当 `api_password` **未设置**时，所有 `/api/v1/admin/*` 端点默认返回 `401 Unauthorized`，响应体包含提示信息。推荐的使用方式：

| 场景 | 做法 |
| --- | --- |
| 生产部署 | 设置 `SOUWEN_API_PASSWORD=<强随机串>`，使用 `Authorization: Bearer <password>` 访问 |
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
