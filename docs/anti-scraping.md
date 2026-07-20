# 反爬技术栈

> SouWen 集成的反爬绕过方案

## 技术总览

| 技术 | 说明 | 模块 |
|------|------|------|
| **TLS 指纹模拟** | curl_cffi impersonate Chrome 120/124 | `fingerprint.py` |
| **浏览器指纹库** | 10 个指纹（Chrome + Edge + Safari + Android） | `fingerprint.py` |
| **浏览器请求头** | 13 个头（Sec-CH-UA 系列、Sec-Fetch 系列） | `fingerprint.py` |
| **分层重试** | http (3次) / scraper (5次) / captcha (5次) | `retry.py` |
| **异步会话缓存** | aiosqlite 异步 SQLite 持久化 OAuth Token / Cookie | `session_cache.py` |
| **代理池轮换** | 多代理 URL 随机选取 | `config/models.py` |
| **礼貌爬取** | 随机间隔 + 自适应退避 + 429 处理 | `scraper/base.py` |
| **Playwright 池化** | 按 event loop / browser / proxy 复用浏览器进程 | `browser_pool.py` |

> curl_cffi 为可选依赖，未安装时自动回退到 httpx。

## TLS 指纹模拟

### 问题

许多网站通过 TLS 握手特征（JA3 指纹）识别非浏览器请求。标准 Python HTTP 库（httpx、requests）的 TLS 指纹与真实浏览器差异明显。

### 方案

SouWen 使用 **curl_cffi** 库模拟真实浏览器的 TLS 握手行为：

- `impersonate` 参数支持 chrome124、chrome120、safari17_0 等
- 完整模拟 Chrome 的 TLS 扩展顺序、加密套件选择
- 由 `BrowserFingerprint` 类管理指纹选择

```python
# curl_cffi 使用示例（BaseScraper 内部实现）
from curl_cffi.requests import AsyncSession

async with AsyncSession(impersonate="chrome124") as session:
    response = await session.get(url, headers=fingerprint.headers)
```

## 浏览器指纹库

`BrowserFingerprint` 提供 10 组完整的浏览器指纹，每组包含：

- **User-Agent**：Chrome 146/125、Edge 137、Safari 17.0、Android Chrome
- **Sec-CH-UA** 系列：品牌标识、移动端标识、平台标识
- **Sec-Fetch** 系列：dest、mode、site、user
- **Accept-Language**、**Accept-Encoding**
- **OS 指纹**：Windows NT 10.0、macOS 10_15_7、Linux x86_64、Android 14

### 指纹轮换策略

```python
from souwen.core.fingerprint import get_random_fingerprint

# 每个 BaseScraper 实例创建时随机选取一个指纹
fingerprint = get_random_fingerprint()

# 也可以主动轮换
new_fingerprint = fingerprint.rotate()
```

每个爬虫实例在创建时随机选取一个指纹，所有请求使用相同指纹以保持会话一致性。需要轮换时调用 `rotate()` 获取新指纹。

## Playwright 浏览器池化

`src/souwen/core/browser_pool.py` 提供内置 Playwright browser pool。它按当前
event loop、browser 名称、headless 设置和解析后的 proxy 建立池 key；同一个 key
复用一个浏览器进程，每次调用创建独立 browser context / page，避免跨任务共享
cookie、localStorage 或页面状态。

关键行为：

- lazy import：只有实际请求浏览器 page 时才导入 `playwright.async_api`；
- 可选运行时：未安装 Playwright 或浏览器 runtime 时抛出配置/运行时错误，调用方应把它当作 fallback 能力；
- 并发上限：默认同一池最多 2 个并发 page，可用 `SOUWEN_BROWSER_POOL_MAX_PAGES` 覆盖；
- 代理隔离：`sources.<name>.proxy` / 全局 `proxy` 会进入 pool key，不同代理不会共用同一浏览器进程；
- 关闭入口：长期进程可调用 `close_browser_pools()` 关闭当前 event loop 上的所有浏览器池。

当前内置使用方是 `google_patents`：XHR 与静态 HTML 都没有结果或失败时，会机会性使用
Playwright 动态渲染搜索页；如果 Playwright 缺失、浏览器启动失败或动态渲染仍被反爬拦截，
会降级返回静态路径结果。动态渲染页会安装请求拦截，对 navigation、子资源、XHR/fetch 等
浏览器请求复用 `validate_fetch_url()`，命中内网、回环、link-local 或保留地址时 abort。

## 自适应退避

`BaseScraper` 实现了自适应退避策略：

```
基础延迟 = random.uniform(min_delay, max_delay)  # 默认 2-5 秒
实际延迟 = 基础延迟 × backoff_multiplier

遇到 429:  backoff_multiplier × 2  （最大 16×）
请求成功:  backoff_multiplier × 0.8 （渐进恢复，不突然重置）
```

这种渐进恢复策略避免了"成功后立即高频请求→再次被限"的振荡问题。

## 分层重试策略

不同场景使用不同的重试参数：

| 级别 | 装饰器 | 最大次数 | 退避范围 | 触发条件 |
|------|--------|----------|----------|----------|
| HTTP | `http_retry` | 3 | 2-10s | Timeout、连接错误、5xx |
| 爬虫 | `scraper_retry` | 5 | 5-30s | 429、Timeout、连接错误 |
| CAPTCHA | `captcha_retry` | 5 | 5-30s | RuntimeError、Timeout |
| 轮询 | `poll_retry` | 可配 | 固定间隔 | 异步任务状态检查 |

## 代理池轮换

通过配置多个代理 URL 实现 IP 轮换：

```yaml
general:
  proxy_pool:
    - http://proxy1:7890
    - http://proxy2:7890
    - socks5://proxy3:1080
```

每次请求随机选取一个代理，分散请求来源。对于高风险目标（如 Google），强烈建议配置代理。

## SSRF 防护（fetch / provider direct URL calls / links / sitemap / wayback）

`/api/v1/fetch`、provider 的 direct URL 调用（如 `fetch` / `scrape` / `extract` /
`contents` / `reader` / `find_similar` / `map` / `crawl`）、`/links`、`/sitemap`、
Wayback fetch 和 Wayback Save Page Now 在实际抓取、调用第三方提取/爬取服务或触发
存档前调用 `souwen.web.fetch.validate_fetch_url(url)`：

1. 仅允许 `http` / `https` scheme；
2. DNS 解析所有 A/AAAA 记录；
3. 拒绝**任一**解析结果落在私有段（10/8、172.16/12、192.168/16）、回环（127/8、::1）、链路本地（169.254/16、fe80::/10）、文档/保留段或组播段；
4. 直连 host 会拒绝非规范 IPv4 数字写法（如 `0177.0.0.1`、`008.0.0.1`、`1.1.1`、`2130706433`、`0x7f000001`），避免不同系统 resolver 对 octal、hex、短写 IPv4 的解释差异造成绕过；
5. IPv4-mapped IPv6、NAT64 well-known prefix、6to4、Teredo 等嵌入 IPv4 的地址会同时按外层 IPv6 和内层 IPv4 判定，避免 `::ffff:127.0.0.1` 这类包装地址绕过；
6. 直连 URL 仍拒绝 `198.18.0.0/15`，但域名 DNS 解析到该 fake-IP/benchmark 网段时允许通过，以兼容 Clash 等本机 fake-IP DNS 代理；
7. 重定向跟随过程中**逐跳**重新校验，防止多跳 SSRF；
8. `jina_reader`、`firecrawl`、`exa`、`tavily`、`xcrawl`、`crawl4ai`、`scrapling`、`scrapfly`、`diffbot`、`scrapingbee`、`zenrows`、`scraperapi`、`apify`、`cloudflare_browser`、`metaso`、`mcp` 和 `kimi_code` 等 provider direct URL calls 在把目标 URL 交给第三方 API、本地浏览器或远程 MCP tool 前会先拦截；能承载 `FetchResult` / `FetchResponse` 的路径返回 blocked result，原始 dict 或 search-style direct 方法则抛出明确 `SSRF 校验失败` 错误；
9. `scrapling` 的 `dynamic` / `stealthy` 浏览器模式会在 Playwright `page_setup` 中安装请求拦截，对 navigation、子资源、XHR/fetch 等浏览器请求复用同一 URL 校验，命中内网/回环/link-local/保留地址时 abort。

Wayback CDX 历史快照查询是 archive.org 元数据查询，仍保留 `example.com` 和
通配符等 CDX 查询形式；会触发内容抓取或外部存档的 Wayback fetch/save 路径会先拒绝
内部、回环、链路本地和保留地址。

被 SSRF 拦截的 URL 仍会出现在响应的 `results` 中，但 `error` 字段会标注 `ssrf_blocked` 类的原因，方便客户端区分。

## WARP（Cloudflare 代理）

WARP 是 SouWen 可控出口网络层的一种实现，可通过本地 SOCKS5/HTTP 代理或外部 sidecar 代理接入。当前支持五种模式：

| 模式 | 实现 | 需要权限 | 适用场景 |
|------|------|---------|----------|
| `wireproxy` | 用户态 WireGuard → SOCKS5 | 无 | 任何容器 / 主机，开箱即用 |
| `kernel` | 内核 WireGuard + microsocks | `NET_ADMIN` + `/dev/net/tun` | 高吞吐场景，性能更好 |
| `usque` | MASQUE/QUIC → SOCKS5，可选 HTTP | 无 | WireGuard UDP 受限或需要 HTTP 代理端口 |
| `warp-cli` | Cloudflare 官方客户端 + GOST 转发 | 依赖官方客户端和 GOST | 需要 WARP+ / ZeroTrust / 官方客户端能力 |
| `external` | 使用已有 SOCKS5/HTTP 代理 | SouWen 侧无特权要求 | 已有 WARP sidecar 或共享代理服务 |
| `auto` | 自动选择可用模式 | — | 未显式指定模式时使用 |

完整部署对比、配置项和限制见 [warp-solutions.md](./warp-solutions.md)。

### 启动方式

**方式 A — 容器入口脚本（推荐）**

`scripts/warp-init.sh` 由 `entrypoint.sh` 调用，根据环境变量自动准备 wireproxy、kernel、usque、warp-cli 或 external 代理：

```bash
docker run -d \
  -e WARP_ENABLED=1 \
  -e WARP_MODE=auto \
  -e WARP_SOCKS_PORT=1080 \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -p 8000:49265 \
  ghcr.io/blueskyxn/souwen
```

入口脚本会把状态写入 `/run/souwen-warp.json`，Python 端的 `WarpManager` 启动时通过 `reconcile()` 同步。

**方式 B — 运行时通过管理 API 切换**

```bash
# 启用（使用 admin_password）
curl -X POST 'http://localhost:8000/api/v1/admin/warp/enable?mode=auto&socks_port=1080' \
     -H "Authorization: Bearer $ADMIN_PASSWORD"

# 查询状态
curl 'http://localhost:8000/api/v1/admin/warp' -H "Authorization: Bearer $ADMIN_PASSWORD"

# 禁用
curl -X POST 'http://localhost:8000/api/v1/admin/warp/disable' -H "Authorization: Bearer $ADMIN_PASSWORD"
```

`get_status()` 返回 `{status, mode, owner, socks_port, ip, pid, interface, last_error, available_modes}`，`owner` 字段用于区分进程归属（`shell`=容器入口启动，`python`=运行时管理 API 启动）。

### 让单源走 WARP

不必把整个 SouWen 走 WARP，直接在频道配置里把高风险源切到 WARP：

```yaml
sources:
  google:        { proxy: warp }
  baidu:         { proxy: warp }
  google_patents:{ proxy: warp }
  twitter:       { proxy: warp }
```

`SouWenConfig.resolve_proxy(source)` 在解析 `proxy: warp` 时会返回 `socks5://localhost:{warp_socks_port}`，再交给 `BaseScraper` / `SouWenHttpClient`。

## 数据源专属网络要求

| 源 | 网络/反爬要求 | 建议配置 |
|----|--------------|----------|
| `google`, `bing`, `baidu`, `yandex`, `mojeek` | 高风险 SERP，IP 容易被 Captcha | `http_backend: curl_cffi` + `proxy: warp` 或代理池 |
| `google_patents` | JS 渲染 + Captcha 风控 | `http_backend: curl_cffi`；安装 Playwright runtime 后可自动启用内置动态渲染 fallback；仍建议配 `proxy: warp` 或代理池 |
| `twitter / x` | 必须官方 Bearer Token，地区限制 | 配 `twitter_bearer_token` + WARP |
| `bilibili` | 部分接口要求授权 + 风控（403 RiskControl） | 设置 `bilibili_sessdata`，控制频率 |
| `duckduckgo` | 偶发风控弹窗，对 TLS 指纹敏感 | `http_backend: curl_cffi` |
| `cnipa` (中国知识产权局) | OAuth + 仅大陆 IP 可达 | 关闭 WARP；走大陆出口或不配代理 |
| `wayback` | IA 全局速率约 15 次/分钟 | 控制 `archive_save` 调用频率 |

## 全局开关与可选依赖

```bash
# 完整安装（含 TLS 指纹 + 网页抓取）
pip install -e .[scraper,web]

# 仅 TLS 指纹
pip install -e .[tls]
```

未安装 `curl_cffi` 时所有爬虫源会自动回退 `httpx`，TLS 指纹模拟将被禁用——只要没把 `default_http_backend` 强制设为 `curl_cffi`，即可正常运行。

## 交叉引用

- 代理 / 频道配置语义：[configuration.md](./configuration.md#数据源频道配置sources)
- WARP 管理 REST 端点：[api-reference.md](./api-reference.md#post-apiv1adminwarpenable)
- 添加新 scraper 类源：[adding-a-source.md](./adding-a-source.md)
