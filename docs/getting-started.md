# 快速开始

本文给出从安装到第一次调用的最短路径。完整配置字段见
[configuration.md](./configuration.md)，完整数据源清单见
[data-sources.md](./data-sources.md)。

## 安装

```bash
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e ".[edition-pro]"
```

只使用 Python library 和 CLI 时可以先安装核心包：

```bash
pip install -e .
```

也可以按功能档位安装常用依赖组合：

```bash
pip install -e ".[edition-basic]"          # 零 Key / 最小依赖体验
pip install -e ".[edition-pro]"            # API 服务 + MCP + TLS 指纹 + scraper 基础能力
```

需要 Crawl4AI、Scrapling、PDF、文章抽取、web2pdf 等 full 能力时，再按目标
browser provider 选择 full 变体。`crawl4ai` 与 `scrapling` 当前依赖树互斥，
不要在同一个环境里同时安装：

```bash
pip install -e ".[edition-full-crawl4ai]"
pip install -e ".[edition-full-scrapling]"
```

## CLI 搜索

```bash
souwen search paper "transformer" --limit 5
souwen search patent "quantum computing" --limit 5
souwen search web "python asyncio" --limit 5
souwen sources --available-only
```

`souwen sources --json` 返回与 `/api/v1/sources` 一致的 Source Catalog
结构，适合前端、脚本和部署检查复用。`--available-only` 只保留静态
edition/config/credentials gate 与当前 runtime importability 同时通过的条目；它不执行联网探测。

## Python 调用

```python
import asyncio

from souwen.search import search, search_all
from souwen.web.fetch import fetch_content


async def main() -> None:
    papers = await search("transformer", domain="paper", limit=5)
    mixed = await search_all("quantum", domains=["paper", "web", "knowledge"], per_domain_limit=5)
    pages = await fetch_content(["https://example.com"], providers=["builtin"])
    print(papers[0].source, len(mixed), pages.total_ok)


asyncio.run(main())
```

## API Server

```bash
SOUWEN_ADMIN_PASSWORD=adminpass souwen serve --host 0.0.0.0 --port 8000
```

常用端点：

```bash
curl "http://localhost:8000/api/v1/search/paper?q=transformer&per_page=5"
curl "http://localhost:8000/api/v1/search/web?q=python&per_page=5"
curl "http://localhost:8000/api/v1/sources"
curl "http://localhost:8000/api/v1/fetch" \
  -H "Authorization: Bearer adminpass" \
  -H "Content-Type: application/json" \
  -d '{"urls":["https://example.com"],"providers":["builtin"]}'
```

`/api/v1/fetch`、`/api/v1/links` 和 `/api/v1/sitemap` 属于管理端抓取能力，需要 Admin Bearer Token。需要同时保护搜索和 `/api/v1/sources` 时，再设置 `SOUWEN_USER_PASSWORD`。

启动后访问 `/docs` 查看 OpenAPI，访问 `/panel#/` 使用 Web Panel。

## 认证

服务端采用 Guest/User/Admin 三角色模型：

| 角色 | 配置 | 用途 |
|---|---|---|
| Guest | `guest_enabled=true` | 允许无 Token 搜索 |
| User | `user_password` | 访问搜索和 `/api/v1/sources` |
| Admin | `admin_password` | 访问 `/api/v1/admin/*` |

请求格式：

```bash
curl -H "Authorization: Bearer $SOUWEN_USER_PASSWORD" \
  "http://localhost:8000/api/v1/sources"
```

生产部署建议至少设置 `SOUWEN_ADMIN_PASSWORD`；本地临时联调可以用
`SOUWEN_ADMIN_OPEN=1` 明确开放管理端点。
