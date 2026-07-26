# 快速开始

本文给出从安装到第一次调用的最短路径。完整配置字段见
[configuration.md](./configuration.md)，完整数据源清单见
[data-sources.md](./data-sources.md)。

## 安装

```bash
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen
pip install -e ".[server,tls,web,robots,scraper]"
```

只使用 Python library 时可以先安装核心包：

```bash
pip install -e .
```

默认 SDK/核心安装不需要可选 runtime；Server 与 provider 按 leaf extra 显式安装：

```bash
pip install -e .                            # 默认 SDK/核心安装
pip install -e ".[server,tls,web,robots,scraper]"  # API Server + TLS + fetch/scraper runtime
```

需要 Crawl4AI、Scrapling 或文章抽取时，再按具体 provider 安装。`crawl4ai` 与 `scrapling` 当前依赖树互斥，
不要在同一个环境里同时安装：

```bash
pip install -e ".[server,tls,web,robots,scraper,newspaper,readability]"
pip install -e ".[server,tls,web,robots,scraper,crawl4ai]"
pip install -e ".[server,tls,web,robots,scraper,scrapling]"
```

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
SOUWEN_ADMIN_PASSWORD=adminpass uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
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
