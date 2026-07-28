# Python REST SDK

SouWen v2rc3 的 Python SDK 由
[`contracts/openapi/souwen-openapi-2.0.0rc3.json`](../contracts/openapi/souwen-openapi-2.0.0rc3.json)
确定性生成。同步 `SouWenClient` 与异步 `AsyncSouWenClient` 覆盖同一组 8 个 operation，模型、
operation mapping、SDK version、API major 与 OpenAPI SHA 都来自这一份 artifact。

## 同步与异步调用

```python
from souwen import SouWenClient
from souwen.delivery.client_sdk import SearchRequest

with SouWenClient("https://souwen.example", token="your-user-token") as client:
    page = client.search(SearchRequest(query="retrieval", domains=["paper", "web"]))
```

```python
from souwen import AsyncSouWenClient
from souwen.delivery.client_sdk import FetchRequest

async with AsyncSouWenClient("https://souwen.example", token="your-user-token") as client:
    batch = await client.fetch(FetchRequest(targets=["https://example.com"]))
```

客户端默认使用 `Authorization: Bearer`。当上游 private edge 占用该 header 时，必须显式使用
两个独立 channel；SDK 不会在失败后自动 fallback：

```python
client = SouWenClient(
    "https://private-space.example",
    token="your-application-token",
    auth_channel="x-souwen-token",
    edge_token="your-private-edge-token",
)
```

不要把 token 写入源码、日志、截图或报告；示例值仅表示参数位置。

## 兼容与错误

- SDK 固定支持 API major `2`，每个请求发送 `X-SouWen-API-Major: 2`。
- 第一次 Data API 调用前自动请求 `/healthz`；major 缺失/不匹配时抛
  `ApiMajorMismatchError`，legacy rollout 或 request/context 不一致时抛
  `ContractViolationError`，业务 body 不会先行发送。
- canonical 非 2xx 响应抛 `SouWenAPIError`，保留 typed `ErrorResponse`、request ID、
  `Retry-After` 和 rate-limit headers。
- 网络与 timeout 失败抛 `SouWenTransportError`。SDK 不自动重试 Search、LLM Search 或 Fetch，
  避免静默重放配额或费用相关操作。
- 默认 timeout 为 125 秒；每个 method 可显式覆盖。同步客户端使用 `close()`/`with`，异步客户端
  使用 `aclose()`/`async with`。

## 生成与验证

生成文件不可手改。维护者在安装 dev 依赖后运行：

```bash
PYTHONPATH=src python3 tools/gen_client_sdk.py --write
PYTHONPATH=src python3 tools/gen_client_sdk.py --check
PYTHONPATH=src python3 scripts/ci/run_profile.py --profile sdk-contract
```

`--check` 会重新读取 canonical artifact，以仓库固定的 Ruff 版本格式化内存中的生成结果，再与
tracked bindings 逐字节比较。未知 operation、非 target security/header、API major/version 漂移或
无法安全映射的 schema 会 fail closed。
