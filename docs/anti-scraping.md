# 反爬技术栈

> SouWen 集成的反爬绕过方案

## 技术总览

| 技术 | 说明 | 模块 |
|------|------|------|
| **TLS 指纹模拟** | curl_cffi impersonate Chrome 120/124 | `fingerprint.py` |
| **浏览器指纹库** | 10 个指纹（Chrome + Edge + Safari + Android） | `fingerprint.py` |
| **浏览器请求头** | 13 个头（Sec-CH-UA 系列、Sec-Fetch 系列） | `fingerprint.py` |
| **Playwright 池化** | 单例复用 Chromium 实例，减少启动开销 | `scraper/browser_pool.py` |
| **分层重试** | http (3次) / scraper (5次) / captcha (5次) | `retry.py` |
| **异步会话缓存** | aiosqlite 异步 SQLite 持久化 OAuth Token / Cookie | `session_cache.py` |
| **代理池轮换** | 多代理 URL 随机选取 | `config.py` |
| **礼貌爬取** | 随机间隔 + 自适应退避 + 429 处理 | `scraper/base.py` |

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
from souwen.fingerprint import get_random_fingerprint

# 每个 BaseScraper 实例创建时随机选取一个指纹
fingerprint = get_random_fingerprint()

# 也可以主动轮换
new_fingerprint = fingerprint.rotate()
```

每个爬虫实例在创建时随机选取一个指纹，所有请求使用相同指纹以保持会话一致性。需要轮换时调用 `rotate()` 获取新指纹。

## Playwright 浏览器池化

`_BrowserPool` 单例管理 Chromium 实例，用于需要 JavaScript 渲染的场景（如 Google Patents）：

- **单例模式**：避免重复启动浏览器的开销
- **实例复用**：多个爬虫共享同一 Chromium 进程
- **资源管理**：自动清理过期页面

安装方式：

```bash
pip install souwen[scraper]
playwright install chromium
```

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
