# SouWen 搜文

**[English](README.en.md)** | 中文

> 给 AI Agent 用的免费搜索与抓取工具：`search` 与 `fetch` 两个动作，
> MCP 与 HTTP API 两个入口，一项看家本领——让免费源在 WARP、代理和无头浏览器下确实能用。

[![Python](https://img.shields.io/badge/python-≥3.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-3.0.0a1-orange)](CHANGELOG.md)

**作者**: [@BlueSkyXN](https://github.com/BlueSkyXN) · **项目地址**: [github.com/BlueSkyXN/SouWen](https://github.com/BlueSkyXN/SouWen) · **协议**: [GPLv3](LICENSE)

> **声明：本项目仅供学习与技术研究使用。** 请勿用于违反法律法规或第三方服务条款的用途。
> 所有数据均来自各源的公开接口，SouWen 不代理任何需要凭据的内容。

---

## 目录

- [简介](#简介)
- [接入 MCP](#接入-mcp)
- [HTTP API](#http-api)
- [Python](#python)
- [安装与部署](#安装与部署)
- [配置](#配置)
- [源与体检](#源与体检)
- [架构](#架构)
- [License](#license)

---

## 简介

SouWen 只做两件事：

- **`search(query, domain, limit)`** —— 在一个领域里并发调用多个免费源，按规范化 URL
  去重合并，失败自动换下一批源。领域：`web`、`news`、`paper`、`patent`、`book`、
  `code`、`community`、`wiki`、`images`、`videos`。
- **`fetch(url, max_chars, start)`** —— 抓一个 URL 的正文（Markdown），长页用 `start`
  续读；站点处理器（arxiv 论文页）优先，之后是通用抓取，页面不可达时走 wayback 兜底。

背后是一套出口阶梯：`direct → impersonate（curl_cffi 指纹）→ proxy（WARP / 用户代理）→
browser（Playwright Chromium）`。免费源最常见的死法是被数据中心 IP 拦截——阶梯在单次
请求内自动升级出口，进程内记住每个主机最近可用的级别。未装 Chromium 或未配置代理时，
对应级别自动跳过。

<!-- BEGIN AUTO: SOURCE METRICS -->
- **36 个内置 Provider v2 package**，共 **36 个 capability adapter**。
  - Search：**32** 个 package · LLM Search：**0** 个 · Fetch：**4** 个。
<!-- END AUTO: SOURCE METRICS -->

## 接入 MCP

stdio 方式（Claude Code、Codex 等宿主）：

```json
{
  "mcpServers": {
    "souwen": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/BlueSkyXN/SouWen", "souwen", "mcp"]
    }
  }
}
```

MCP 恰好暴露两个工具：

- `search(query, domain="web", limit=8)` —— 返回编号结果（标题、URL、摘要；论文带年份作者）。
- `fetch(url, max_chars=20000, start=0)` —— 返回元信息行 + 正文；被截断时末行提示下一次
  调用应传的 `start`。

源清单与健康状态走 `souwen://sources` 资源，不占工具位。

## HTTP API

```bash
pip install "souwen[server,mcp]"   # 或 docker（见下）
souwen serve --port 8000
```

| 路由 | 说明 |
|---|---|
| `POST /search` | `{"query": "...", "domain": "web", "limit": 8}` → `{"results": [...], "sources": [...], "partial": bool}` |
| `POST /fetch` | `{"url": "...", "max_chars": 20000, "start": 0}` → `{"title", "url", "content", "total_chars", "start", "next_start", "egress"}` |
| `GET /sources` | 每个源的领域与可用性 |
| `GET /healthz` | 探针 |
| `/mcp` | MCP streamable HTTP |

鉴权：配置 `user_password`（环境变量 `SOUWEN_USER_PASSWORD`）后，所有请求需
`Authorization: Bearer <password>` 或 `X-SouWen-Token`；不配置则开放（沿用既有 user
凭据校验行为，不放宽）。

## Python

```python
from souwen import search, fetch

results = await search("attention is all you need", domain="paper", limit=8)
page = await fetch("https://arxiv.org/abs/1706.03762", max_chars=20000)
```

## 安装与部署

```bash
# 库（搜索 + 抓取）
pip install "souwen[tls,web]"
# MCP server
pip install "souwen[mcp]"
# HTTP 服务（含 /mcp）
pip install "souwen[server,tls,web,robots,scraper]"
# 无头浏览器级出口
pip install "souwen[browser]" && playwright install chromium

# Docker（内置 WARP 组件与 Chromium）
docker build -t souwen . && docker run -p 49265:49265 -e SOUWEN_USER_PASSWORD=... souwen
```

## 配置

最小配置即可运行（全部零 Key 源）。`souwen.example.yaml` 是完整模板：
搜索候选顺序（`search_defaults`，随体检更新）、WARP 模式（wireproxy / usque / external）、
按源的频道覆盖（`sources.<id>.{enabled, proxy, timeout, api_key, ...}`）。
需免费 Key 的源（patentsview、epo_ops、uspto_odp、youtube）默认关闭，配置对应 key 才启用。

## 源与体检

36 个存活源（32 搜索 + 4 抓取）每周由 `census.yml` 在权威环境（构建镜像、WARP 开、
零 Key）自动体检：sources / domains / fetch 三种模式，PASS/WARN/FAIL 判定，报告即
[docs/sources.md](docs/sources.md) 的数据来源。体检判死的源按规则删除——本仓库不保留
没验证过能用的源。

## 架构

```
src/souwen/
  agent.py          门面：search / fetch / sources（MCP、HTTP、Python 共用）
  cli.py            souwen mcp | serve | doctor
  modules/search    领域选源、并发、合并去重、回退、紧凑投影
  modules/fetch     站点处理器 → 通用抓取 → 提取链 → 分页缓存
  common_runtime/   传输、egress 阶梯、SSRF、限流、WARP 支持
  providers/        一个源一个包（声明 + spec + adapter）与私有 client
  server/           FastAPI 路由、鉴权、限流、MCP server、doctor
```

SSRF 校验（`common_runtime/security/fetch_target.py`）不可关闭：HTTP、浏览器（含每跳
重定向）一律先校验后连接，浏览器流量经回环代理 pin 到已校验 IP。

## License

[GPLv3](LICENSE)
