# Python API

公开 Python API 是由 frozen OpenAPI 生成的 SDK，不承诺 provider client、registry 或
旧搜索 facade 的 direct import。同步客户端 `SouWenClient` 和异步客户端
`AsyncSouWenClient` 都只提供 Search、LLM Search、Fetch、Providers 与 probes。

```python
from souwen import SouWenClient
from souwen.delivery.client_sdk import SearchRequest

with SouWenClient("http://127.0.0.1:8000", token="user-token") as client:
    page = client.search(SearchRequest(query="quantum computing", domains=["paper"]))
    providers = client.list_providers()
```

SDK 在业务请求前通过 `/healthz` 校验 API major。Provider 选择和可用性必须读取
`list_providers()`；它对应 `GET /api/v1/providers`，而不是已退休的 `/sources`。
Provider catalog 的 source of truth 是 `ProviderManifest` catalog、`ManifestRegistry` 和
`ProviderManager`。
