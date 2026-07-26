# 快速开始

SouWen 是 target-only v2 服务：公开数据能力只有 Search、LLM Search 和 Fetch。
Python 入口是 generated SDK；Provider 由 `ProviderManifest` catalog、`ManifestRegistry`
和 `ProviderManager` 管理。

```bash
pip install -e ".[server,tls,web,robots,scraper]"
SOUWEN_USER_PASSWORD=userpass SOUWEN_ADMIN_PASSWORD=adminpass \
  uvicorn souwen.server.app:app --host 0.0.0.0 --port 8000
```

```python
from souwen import SouWenClient
from souwen.delivery.client_sdk import SearchRequest

with SouWenClient("http://127.0.0.1:8000", token="userpass") as client:
    page = client.search(SearchRequest(query="transformer", domains=["paper"]))
```

数据 API 使用 user credential 和 `X-SouWen-API-Major: 2`：

```bash
curl http://127.0.0.1:8000/api/v1/providers \
  -H 'Authorization: Bearer userpass' \
  -H 'X-SouWen-API-Major: 2'
```

可用操作是 `POST /api/v1/search`、`POST /api/v1/llm-search`、
`POST /api/v1/fetch` 和 `GET /api/v1/providers`。使用 `/healthz`、`/readyz` 探测；
`/health`、`/readiness` 是 2.x alias。Admin 只有 read-only
`GET /api/v1/admin/config`、`/doctor`、`/ping`。没有 rollout switch、`/sources`、
citation/detail/archive-save、recursive crawl、browser-fetch product entry 或旧 enriched search。
