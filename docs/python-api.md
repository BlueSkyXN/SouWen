# Python API

本文列出推荐的 Python 调用入口。完整模型字段和 REST 端点见
[api-reference.md](./api-reference.md)。

## 搜索

```python
from souwen.search import search, search_all, search_by_capability

papers = await search("transformer", domain="paper", limit=5)
web = await search("python asyncio", domain="web", capability="search", limit=5)
news = await search_by_capability("AI news", capability="search_news", limit=5)
mixed = await search_all("quantum computing", domains=["paper", "web"], limit=5)
```

`search()` 返回按源聚合的 `SearchResponse` 列表。单个源失败不会阻断其他源。

## 抓取

```python
from souwen.web.fetch import fetch_content

resp = await fetch_content(
    ["https://example.com"],
    providers=["builtin", "readability"],
    strategy="fallback",
)
```

`strategy="fallback"` 会按 provider 顺序补抓失败项；`strategy="fanout"` 会并发
返回所有 provider 结果。

## 网页归档

```python
from souwen.web.wayback import WaybackClient

async with WaybackClient() as wayback:
    snapshots = await wayback.query_snapshots("https://example.com", limit=5)
```

## 配置

```python
from souwen.config import get_config, reload_config

config = get_config()
print(config.timeout)

config = reload_config()
```

配置优先级和字段表见 [configuration.md](./configuration.md)。

## Source Catalog

```python
from souwen.config import get_config
from souwen.registry.catalog import public_source_catalog_payload

payload = public_source_catalog_payload(get_config())
for source in payload["sources"]:
    if source["available"] and "search" in source["capabilities"]:
        print(source["name"], source["category"])
```

该 payload 与 `/api/v1/sources` 和 `souwen sources --json` 保持一致。
