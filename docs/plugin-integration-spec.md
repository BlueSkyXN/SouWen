# SouWen 插件对接规范 (Plugin Integration Spec)

> 本文是 SouWen 外部插件的**对接契约**：定义插件如何被发现、如何声明数据源 / fetch
> provider、Client 与 handler 的方法签名，以及配置、错误处理、打包和测试要求。
> 本文不涉及任何具体插件的实现细节——具体插件请见各自仓库的 README。

---

## 1. 概述与目标

SouWen 的所有数据源都通过 [`SourceAdapter`](../src/souwen/registry/adapter.py) 在
`registry/sources/` 集中声明（"单一事实源"）。**插件机制**允许第三方在 SouWen 主仓
之外贡献新的 `SourceAdapter` 与 fetch handler，常见场景：

- 接入私有 / 内部 / 商业搜索 API
- 为 `fetch` 域加入新的抓取后端（如自建无头浏览器、内部缓存、PDF 渲染）
- 临时实验某个新源，稳定后再合并到上游

**一个完整的插件 = 一个 `SourceAdapter`（+ 可选的 `FetchHandler` 注册）**。
插件加载完全异常隔离：单个插件失败 / 重名只记 warning，不影响 SouWen 启动。

---

## 2. 插件发现机制

插件被加载到 registry 有两条路径，**二选一或并用**：

| 路径 | 触发方式 | 适用场景 |
|---|---|---|
| **Entry Points 自动发现** | `pip install` 后即生效 | 公开发布到 PyPI / Git；零配置体验 |
| **配置 / 环境变量手动指定** | `souwen.yaml` 的 `plugins` 字段或 `SOUWEN_PLUGINS` 环境变量 | 私有脚本、单文件实验、临时调试 |

### Entry Point 分组

固定为 **`souwen.plugins`**（见 [`src/souwen/plugin.py`](../src/souwen/plugin.py) 的
`ENTRY_POINT_GROUP` 常量）：

```toml
[project.entry-points."souwen.plugins"]
my-source = "my_plugin:plugin"
```

### 双模式加载（运行时发现 vs 打包嵌入）

同一份 entry_points 声明支持两种部署形态，二者使用**完全相同**的发现机制：

| 模式 | 安装方式 | 适用场景 |
|---|---|---|
| **运行时发现** | `pip install superweb2pdf` 单独安装第三方包 | 已发布到 PyPI；插件随宿主升级解耦；社区分发 |
| **打包嵌入（optional dependency）** | `pip install "souwen[web2pdf]"` | Docker 镜像 / 一键部署；插件依赖随 SouWen extras 自动安装 |

**Docker / 多 extras**：`pip install ".[server,tls,web2pdf]"`。

要把插件挂到 SouWen 的 optional dependencies 上，宿主项目在 `pyproject.toml`
中追加（仅 SouWen 主仓维护者关心）：

```toml
[project.optional-dependencies]
web2pdf = ["superweb2pdf[capture]>=0.2.0"]
```

无论哪种模式，启动时 SouWen 都通过 `importlib.metadata.entry_points(group="souwen.plugins")`
扫描发现。**插件作者通常只需声明 entry_points**，是否打包嵌入由宿主决定。

### Entry Point 目标可以是四种形态

| 形态 | 示例 | 用途 |
|---|---|---|
| `Plugin` 实例 | `plugin = Plugin(name="my_plugin", adapters=[...])` | 需要生命周期、配置 schema 或健康检查 |
| `SourceAdapter` 实例 | `adapter = SourceAdapter(...)` | 单源插件 |
| 零参 callable 返回 `Plugin` / `SourceAdapter` | `def make() -> Plugin` | 需要运行时构造 |
| 零参 callable 返回 `list[SourceAdapter]` | `def make_all() -> list[SourceAdapter]` | 一次注册多个源 |

### 加载流程

```
registry/__init__.py 导入
    ↓
1. import sources       —— 触发内置 _reg()，填满 _REGISTRY
    ↓
2. plugin.load_plugins(config)
    ├─ discover_entrypoint_plugins()
    │     扫描 importlib.metadata entry_points(group="souwen.plugins")
    └─ load_config_plugins(config.plugins + SOUWEN_PLUGINS)
          解析 "module:attr" 字符串列表
    ↓
3. _reg_external(adapter)
    重名 → warning 跳过；否则插入 _REGISTRY 并加入 _EXTERNAL_PLUGINS
```

外部插件名出现在 `external_plugins()` 视图中，可用于 CLI / `/sources` 端点审计。

---

## 3. SourceAdapter 合约

`SourceAdapter` 是 `frozen=True, slots=True` 的不可变 dataclass。

### 必填字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `name` | `str` | **全局唯一**；建议小写 + 下划线；避免与内置源冲突 |
| `domain` | `str` | 必须 ∈ `DOMAINS` 或等于 `FETCH_DOMAIN` |
| `integration` | `str` | 必须 ∈ `INTEGRATIONS`：`open_api` / `official_api` / `self_hosted` / `scraper` |
| `description` | `str` | UI / `souwen sources` 展示文案，建议 ≤ 80 字 |
| `config_field` | `str \| None` | 对应 `SouWenConfig` 字段名；零配置插件传 `None` |
| `client_loader` | `Callable[[], type]` | **必须用 `lazy("module:Class")`**（见 §11） |
| `methods` | `Mapping[str, MethodSpec]` | `capability → MethodSpec`，至少一项 |

### 可选字段

| 字段 | 默认 | 约束 |
|---|---|---|
| `extra_domains` | `frozenset()` | 跨域能力；当前仅允许 `frozenset({"fetch"})` |
| `default_enabled` | `True` | UI 默认是否勾选 |
| `default_for` | `frozenset()` | 形如 `{"web:search"}`；外部插件**不建议**抢占默认位 |
| `tags` | `frozenset()` | 见下表；web 插件可用 `category:professional` 进入专业搜索分类 |
| `needs_config` | `None` | 是否"必须配置才能工作"；建议显式声明（`True` / `False`） |
| `auth_requirement` | `None` | `none` / `optional` / `required` / `self_hosted`；None 时从旧字段派生 |
| `credential_fields` | `()` | 完整凭据字段；多字段凭据应列全 |
| `optional_credential_effect` | `None` | 可选凭据收益：`rate_limit` / `quota` / `quality` / `personalization` / `private_access` / `write_access` / `politeness` / `unknown` |
| `risk_level` | `"low"` | `low` / `medium` / `high` |
| `risk_reasons` | `frozenset()` | 风险原因标签，如 `anti_scraping` / `captcha` / `quota_cost` / `requires_browser` |
| `distribution` | `"core"` | 内置或插件推荐分发范围：`core` / `extra` / `plugin`；外部插件运行时会被视为 `plugin` |
| `package_extra` | `None` | 建议 optional dependency 组，如 `browser` / `scraper` |
| `stability` | `"stable"` | `stable` / `beta` / `experimental` / `deprecated` |
| `usage_note` | `None` | 用户级提示文案,在 doctor / API / Panel 中作为状态消息后缀展示。**不参与可用性判定**。`deprecated` / 实验性爬虫建议显式声明,例如 `"公开搜索端点已变更,当前接入待修复"`、`"实验性爬虫,易受反爬影响"` |

### 鉴权、风险与分发建议

`integration` 只描述技术接入方式，不描述凭据强度。插件作者应显式声明 catalog 字段，让 CLI、doctor、API 和 Panel 能给出一致提示：

```python
plugin = SourceAdapter(
    name="my_source",
    domain="web",
    integration="official_api",
    description="My Source Search",
    config_field="my_source_api_key",
    needs_config=False,
    auth_requirement="optional",
    credential_fields=("my_source_api_key",),
    optional_credential_effect="rate_limit",
    risk_level="low",
    distribution="plugin",
    package_extra="my_source",
    stability="stable",
    client_loader=lazy("my_plugin.client:MySourceClient"),
    methods={"search": MethodSpec("search")},
)
```

常见组合：

| 场景 | 推荐声明 |
|---|---|
| 无凭据即可运行 | `auth_requirement="none"` |
| Key 只提升限流或配额 | `auth_requirement="optional"` + `optional_credential_effect="rate_limit"` / `"quota"` |
| 必须凭据 | `auth_requirement="required"` + `credential_fields=(...)` |
| 自建实例 | `auth_requirement="self_hosted"` + `config_field="<source>_url"`；`self_hosted` 必须声明 URL/凭据字段 |
| 高风控/重依赖插件 | `risk_level="medium"` 或 `"high"`，并填写 `risk_reasons` / `package_extra` |

### 推荐 tag

| Tag | 作用 |
|---|---|
| `"external_plugin"` | **强烈建议所有外部插件加上**，便于审计与故障排查 |
| `"high_risk"` | 高风控源，会被 `high_risk_sources()` 视图收录 |
| `"category:professional"` | 仅适用于 `domain="web"` 的插件；进入专业搜索分类 |
| `"category:general"` | 仅适用于 `domain="web"` 的插件；显式进入通用搜索分类（默认也是 general） |

`domain="web"` 的外部插件如果不声明 `category:*`，会按公开 domain 语义归入 `general`。
只有 AI/聚合搜索、商业 SERP API 等更接近内置 `professional` 分类的插件，才建议声明 `category:professional`。

> ⚠️ 不要使用 `v0_category:*` / `v0_all_sources:exclude` 等内置兼容标签——这些仅用于
> 内置源对旧版 `ALL_SOURCES` 的向下兼容。

### 校验时机

`SourceAdapter` 构造时会做枚举值、`auth_requirement`/`credential_fields` 组合、
`extra_domains` 与 `default_for` 格式等基础防呆；`_reg_external()` 注册时只做重名隔离。
`MethodSpec.method_name` 是否存在于 Client、`param_map` 目标参数是否匹配签名等深度契约，
由插件作者在测试中使用 `souwen.testing.assert_valid_plugin()` / `validate_client_contract()` 校验。

### 常量速查

```python
from souwen.registry.adapter import (
    DOMAINS,        # {"paper","patent","web","social","video","knowledge",
                    #  "developer","cn_tech","office","archive"}
    FETCH_DOMAIN,   # "fetch"
    CAPABILITIES,   # {"search","search_news","search_images","search_videos",
                    #  "search_articles","search_users","get_detail","get_trending",
                    #  "get_transcript","fetch","archive_lookup","archive_save"}
    INTEGRATIONS,   # {"open_api","scraper","official_api","self_hosted"}
    AUTH_REQUIREMENTS,
    OPTIONAL_CREDENTIAL_EFFECTS,
    RISK_LEVELS,
    RISK_REASONS,
    DISTRIBUTIONS,
    STABILITIES,
)
```

非标准 capability 用命名空间形式：`"my_source:semantic_search"`，不会进入门面自动派发。

---

## 4. MethodSpec 合约

```python
@dataclass(frozen=True, slots=True)
class MethodSpec:
    method_name: str                                       # Client 上的方法名
    param_map: Mapping[str, str] = {}                      # 入参重命名
    pre_call: Callable[[dict], dict] | None = None         # 复杂变换逃生舱
```

| 字段 | 约束 |
|---|---|
| `method_name` | Client 类上必须存在 `async def <method_name>(self, **kwargs)` |
| `param_map` | `{统一参数名: Client 实参名}`；典型如 `{"limit": "per_page"}` |
| `pre_call` | 接收 dict 返回 dict；用于 `param_map` 不能表达的复杂入参变换 |

### 派发规则

门面层调用顺序：

1. 收集统一参数（如 `query`, `limit`）
2. 应用 `param_map` 重命名
3. 若有 `pre_call`，再 `kwargs = pre_call(kwargs)`
4. `await client.<method_name>(**kwargs)`

---

## 5. Client 合约

Client 是真正执行业务的类，由 `client_loader()` 解析得到。

### 强制约定

- **必须**实现 `async __aenter__(self) -> Self`
- **必须**实现 `async __aexit__(self, *args) -> None`
- **必须**实现 `methods` 中声明的每个方法
- 方法签名应接受经 `param_map` / `pre_call` 重命名后的统一入参

### 模板

```python
from typing import Any
from souwen.config import get_config


class MyClient:
    def __init__(self) -> None:
        self._config = get_config()
        self._source_config = self._config.get_source_config("my_source")

    async def __aenter__(self) -> "MyClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def search(self, query: str, limit: int = 10) -> dict:
        ...
```

### 数据模型

按 capability 选择返回模型，定义在 `souwen.models`：

| Capability | 返回模型 |
|---|---|
| `search` (paper / patent) | `SearchResponse[PaperResult]` 等 |
| `search` (web) | `SearchResponse[WebSearchResult]` |
| `fetch` | `FetchResult` / `FetchResponse` |
| `archive_lookup` | `WaybackCDXResponse` |
| `archive_save` | `ArchiveSaveResponse` |

完整字段见 [`src/souwen/models.py`](../src/souwen/models.py)。

### 配置访问

```python
config = get_config()

# 1. 顶层 flat key
api_key = getattr(config, "my_source_api_key", None)

# 2. 频道级（推荐）：sources.my_source.{enabled, proxy, base_url, api_key, headers, params}
sc = config.get_source_config("my_source")
if not sc.enabled:
    raise RuntimeError("my_source disabled")

# 3. 优先级辅助函数（频道 > flat）
api_key = config.resolve_api_key("my_source", "my_source_api_key")
base_url = config.resolve_base_url("my_source", "https://api.example.com")
```

`SourceChannelConfig` 字段（[`src/souwen/config/models.py`](../src/souwen/config/models.py)）：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | `bool` | `True` | 该源是否启用 |
| `proxy` | `str` | `"inherit"` | `inherit` / `none` / `warp` / 显式 URL |
| `http_backend` | `str` | `"auto"` | `auto` / `httpx` / `curl_cffi` |
| `base_url` | `str \| None` | `None` | 覆盖默认 base URL |
| `api_key` | `str \| None` | `None` | 频道级 API Key（优先级高于 flat key） |
| `headers` | `dict[str, str]` | `{}` | 追加自定义 header |
| `params` | `dict[str, str\|int\|float\|bool]` | `{}` | 自定义参数（plugin 自由解释） |

---

## 6. Fetch Provider 合约

如果插件要作为 fetch provider（`souwen fetch --provider=my-source`），仅声明
`SourceAdapter` 不足以让门面派发——还需要把异步抓取函数注册到
`souwen.web.fetch._FETCH_HANDLERS`。

### Handler 签名

```python
from typing import Any
from souwen.models import FetchResponse

FetchHandler = Callable[..., Awaitable[FetchResponse]]

async def my_handler(
    urls: list[str],
    timeout: float = 30.0,
    **kwargs: Any,
) -> FetchResponse:
    ...
```

- `urls`：要抓取的 URL 列表
- `timeout`：单 URL 超时（秒）
- `**kwargs`：provider 私有参数（`selector` / `start_index` / `max_length` /
  `respect_robots_txt` 等）；不识别的 kwarg 必须忽略，不应抛错

### 注册

```python
from souwen.web.fetch import register_fetch_handler

register_fetch_handler("my-source", my_handler, override=False)
```

| 参数 | 含义 |
|---|---|
| `provider: str` | provider 名（CLI `--provider` 与 `fetch_content(provider=)` 用） |
| `handler: FetchHandler` | 满足 §6 签名的异步函数 |
| `override: bool = False` | 是否允许覆盖同名 handler；默认拒绝并记 warning |

### 注册时机

最稳妥的做法是在插件包 `__init__.py` 顶层调用：

```python
# my_plugin/__init__.py
from souwen.registry.adapter import MethodSpec, SourceAdapter
from souwen.registry.loader import lazy
from souwen.web.fetch import register_fetch_handler
from .handler import my_handler

plugin = SourceAdapter(...)
register_fetch_handler("my-source", my_handler)
```

entry point `ep.load()` 会执行该模块顶层代码，handler 即被注册。

### 何时只用 SourceAdapter（不需要 handler）

- 插件只做**搜索**类 capability，不在 `fetch` 域、不实现 `fetch` capability
- 不希望插件出现在 `fetch_content(provider=...)` 列表里

简言之：`SourceAdapter` 让源出现在 registry，`register_fetch_handler` 让源能被
facade fetch 派发，二者互不依赖；fetch provider 通常需要两个都做。

### 错误处理约定

- 抓取类**禁止外抛异常**：把错误装进 `FetchResult.error: str` 返回
- 单 URL 失败不应拖累 batch 内其他 URL（建议在 handler 内独立 try/except 每个 URL）

---

## 7. 配置规范

### `souwen.yaml`

```yaml
sources:
  my-source:
    enabled: true
    api_key: "sk-..."
    proxy: warp
    params:
      mode: fast
      max_pages: 50

# 手动指定额外插件（entry point 之外）
plugins:
  - "my_plugin:plugin"
  - "experimental.thing:make_adapter"
```

### 环境变量

```bash
# 逗号分隔
export SOUWEN_PLUGINS="my_plugin:plugin,other_pkg.mod:make_adapter"

# 或 JSON 数组
export SOUWEN_PLUGINS='["my_plugin:plugin","other_pkg.mod:make_adapter"]'
```

`SOUWEN_PLUGINS` 与 `souwen.yaml` 的 `plugins` 字段会被合并，去重后一并加载。

#### `SOUWEN_PLUGIN_AUTOLOAD`（仅文档生成 / CI 隔离用，非用户面向）

| 取值 | 行为 |
|---|---|
| 未设置 / `1`（默认） | 启动时自动扫描 `souwen.plugins` entry point |
| `0` | 跳过 entry point 自动发现，仅加载内置源 + 显式 `SOUWEN_PLUGINS` / `souwen.yaml` 路径 |

> ⚠️ **不要在生产 / 运维场景手动设置 `SOUWEN_PLUGIN_AUTOLOAD=0`**。它是
> `tools/gen_docs.py` 内部协议，用于让 checked-in `docs/data-sources.md`
> 在本机装了第三方 entry point 时也保持稳定（详见
> [`tools/gen_docs.py`](../tools/gen_docs.py) 中的 `render` /
> `render_cli_content`）。希望屏蔽某个插件，请用 `souwen.yaml` 的 `plugins`
> 显式列表或 `SOUWEN_PLUGINS` 覆盖，而不是关掉 autoload。

### 字符串路径格式

`"module.path:attribute"`，attribute 三种合法形态见 §2。

---

## 8. 错误处理与隔离

| 错误类型 | SouWen 行为 |
|---|---|
| 插件 import 失败 | 记 warning，跳过；继续加载其他插件 |
| Entry point `ep.load()` 抛异常 | 同上 |
| `name` 与已注册源冲突 | 记 warning，跳过；不覆盖已有源 |
| `_reg_external` 字段类型不合法 | 抛 `TypeError`，被外层 catch 后记 warning |
| Fetch handler 重名注册（`override=False`） | 记 warning，保留旧 handler |

`load_plugins()` 返回值：

```python
{"loaded": ["my-source", "..."], "errors": [{"source": "...", "name": "...", "error": "..."}]}
```

可在启动日志或 `/api/v1/plugins` 端点（如有）中暴露给运维。

### Client / Handler 运行时异常

- 抓取类：禁止外抛，错误装入 `FetchResult.error`
- 搜索类：可抛 `souwen.core.exceptions` 中的标准异常
  （`ConfigError` / `RateLimitError` / `SourceUnavailableError` / `AuthError`），
  门面层会做异常隔离，不影响其他源

---

## 9. 打包规范

### `pyproject.toml` 模板

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-souwen-plugin"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "souwen>=1.0.0",
]

[project.entry-points."souwen.plugins"]
my-source = "my_plugin:plugin"

[tool.hatch.build.targets.wheel]
packages = ["my_plugin"]
```

### 依赖版本约束

- **`souwen>=1.0.0`**：本规范对应的 SouWen 主版本；遵循 SemVer
- **不要把 SouWen 列为 `==` 精确依赖**，避免与宿主 SouWen 版本冲突
- 重 IO 依赖（playwright、selenium、ffmpeg-python 等）应放进 `[project.optional-dependencies]`，
  让用户按需 `pip install my-plugin[browser]`

### 推荐包结构

```
my-souwen-plugin/
├── pyproject.toml
├── README.md
├── my_plugin/
│   ├── __init__.py            # 暴露 plugin: SourceAdapter；可在此注册 fetch handler
│   ├── client.py              # Client 类（async context manager）
│   └── handler.py             # （可选）fetch handler
└── tests/
    └── test_plugin.py
```

### 多源插件

一个包注册多个源有两种写法：

```toml
# 方式 A：多个 entry point
[project.entry-points."souwen.plugins"]
source-a = "my_plugin:adapter_a"
source-b = "my_plugin:adapter_b"

# 方式 B：单 entry point 返回 list
[project.entry-points."souwen.plugins"]
my_plugin = "my_plugin:get_all_adapters"
```

```python
def get_all_adapters() -> list[SourceAdapter]:
    return [adapter_a, adapter_b]
```

---

## 10. 测试清单

每个插件应至少覆盖以下场景：

### 契约校验

```python
from souwen.registry.adapter import SourceAdapter
from my_plugin import plugin

def test_plugin_is_source_adapter():
    assert isinstance(plugin, SourceAdapter)

def test_plugin_name():
    assert plugin.name == "my-source"

def test_client_loader_resolves():
    cls = plugin.client_loader()
    assert hasattr(cls, plugin.methods["search"].method_name)
```

### 注册可用性

```python
import pytest
from souwen.registry import views
from my_plugin import plugin

@pytest.fixture
def registered_plugin():
    ok = views._reg_external(plugin)
    assert ok, "plugin failed to register (name conflict?)"
    yield plugin
    views._REGISTRY.pop(plugin.name, None)
    views._EXTERNAL_PLUGINS.discard(plugin.name)


def test_appears_in_registry(registered_plugin):
    assert views.get(plugin.name) is registered_plugin
    assert plugin.name in views.external_plugins()
```

### 端到端派发（可选）

```python
@pytest.mark.asyncio
async def test_search_via_facade(registered_plugin, httpx_mock):
    from souwen.facade.search import search
    httpx_mock.add_response(url="https://api.example.com/search", json={...})
    resp = await search("hello", domain="web", sources=[plugin.name], limit=3)
    assert len(resp[0].results) > 0
```

### Fetch handler（如适用）

```python
import pytest
from souwen.web.fetch import get_fetch_handlers

def test_fetch_handler_registered():
    import my_plugin  # noqa: F401  触发顶层注册
    assert "my-source" in get_fetch_handlers()
```

---

## 11. API 参考

### `souwen.registry.adapter`

| 名字 | 类型 | 用途 |
|---|---|---|
| `SourceAdapter` | dataclass | 插件主体声明 |
| `MethodSpec` | dataclass | capability → Client 方法适配 |
| `DOMAINS` | `frozenset[str]` | 10 个业务域 |
| `FETCH_DOMAIN` | `str` | `"fetch"`（横切域） |
| `CAPABILITIES` | `frozenset[str]` | 12 个标准 capability |
| `INTEGRATIONS` | `frozenset[str]` | 4 种集成方式 |

### `souwen.registry.loader`

| 名字 | 签名 | 用途 |
|---|---|---|
| `lazy(import_path)` | `(str) -> Callable[[], type]` | 字符串懒加载 Client 类 |

### `souwen.registry.views`

| 名字 | 用途 |
|---|---|
| `external_plugins() -> list[str]` | 所有外部插件名（按字母序） |
| `get(name) -> SourceAdapter \| None` | 按名取 adapter |
| `by_domain(domain) -> list[SourceAdapter]` | 某 domain 全部 adapter |
| `_reg_external(adapter) -> bool` | 内部 API；测试 / 手动加载用，重名返回 False |

### `souwen.web.fetch`

| 名字 | 签名 | 用途 |
|---|---|---|
| `register_fetch_handler(provider, handler, *, override=False)` | `(str, FetchHandler, bool) -> None` | 注册 fetch handler |
| `get_fetch_handlers() -> dict[str, FetchHandler]` | — | 内省全部已注册 handler |
| `FetchHandler` | `Callable[..., Awaitable[FetchResponse]]` | handler 类型签名 |

### `souwen.plugin`

| 名字 | 签名 | 用途 |
|---|---|---|
| `ENTRY_POINT_GROUP` | `"souwen.plugins"` | entry point 分组名 |
| `discover_entrypoint_plugins(group=ENTRY_POINT_GROUP)` | `() -> (loaded, errors)` | 扫描 entry points 并注册 |
| `load_config_plugins(plugin_paths)` | `(list[str]) -> (loaded, errors)` | 加载 `"module:attr"` 字符串列表 |
| `load_plugins(config=None)` | `(SouWenConfig\|None) -> {"loaded": [...], "errors": [...]}` | 总入口（registry 启动时自动调用） |

### `souwen.config`

| 名字 | 用途 |
|---|---|
| `get_config() -> SouWenConfig` | 单例配置访问 |
| `SouWenConfig.get_source_config(name) -> SourceChannelConfig` | 频道级配置 |
| `SouWenConfig.resolve_api_key(name, legacy_field) -> str \| None` | 频道 api_key 优先于 flat key |
| `SouWenConfig.resolve_base_url(name, default) -> str` | 频道 base_url 覆盖 |

### `souwen.models`

`FetchResult` / `FetchResponse` / `SearchResponse` / `PaperResult` /
`WebSearchResult` / `WaybackCDXResponse` 等——见 [`src/souwen/models.py`](../src/souwen/models.py)。

---

## 12. 常见陷阱

- **`client_loader` 直接传 lambda / 类对象**：会让 registry 在导入期就 import 你的
  Client，破坏启动延迟优化。**始终用 `lazy("module:Class")`**。
- **`name` 与内置源冲突**：`_reg_external` 会记 warning 后跳过，插件不生效。
  发布前用 `souwen sources` 检查冲突。
- **fetch provider 忘了注册 handler**：能在 `souwen sources` 看到，但
  `souwen fetch --provider=...` 报"未知提供者"。
- **Client `__aexit__` 不实现**：facade 用 `async with` 调度，缺失会 AttributeError。
- **抓取类异常外抛**：违反 §6 / §8 约定，会触发上层异常隔离但用户看不到具体原因。
- **修改可变默认参**：`SourceAdapter` 是 `frozen=True`，所有 `frozenset()` /
  `Mapping` 都不可变。

---

## 13. 交叉引用

- 架构总览：[architecture.md](architecture.md)
- 添加内置源（仓内贡献）：[adding-a-source.md](adding-a-source.md)
- **运维侧管理（Web Panel / CLI / API）**：[plugin-management.md](plugin-management.md)
- **最小示例插件**：[`examples/minimal-plugin/`](../examples/minimal-plugin/) —— 可直接 `pip install -e .` 体验
- 数据模型：[`src/souwen/models.py`](../src/souwen/models.py)
- 配置字段：[configuration.md](configuration.md)
- 反爬 / TLS 指纹（写 scraper 类插件时）：[anti-scraping.md](anti-scraping.md)

> **Tip：** 你的插件如果需要 `health_check`，请尽可能保持低开销（毫秒级），
> 因为运维会在 Web Panel 与 CLI（`souwen plugins list --health`）批量并发调用。
> `health_check` 支持同步函数直接返回 `dict`，或 `async def` 返回 `dict`；
> 不支持同步函数返回 coroutine。业务侧的"实时探测"应放在专用的 doctor
> 端点，而不是 health_check。
