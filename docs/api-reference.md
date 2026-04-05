# API 接口参考

> SouWen 公开 API、数据模型、CLI 命令与 MCP 工具

## Python API

### 统一搜索入口

```python
from souwen import search, search_papers, search_patents, web_search
```

#### `search(query, domain="paper", **kwargs)` → `list[SearchResponse]`

统一调度器，根据 `domain` 路由到对应搜索函数。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `domain` | `str` | `"paper"` | `"paper"` / `"patent"` / `"web"` |
| `**kwargs` | — | — | 传递给对应搜索函数 |

#### `search_papers(query, sources=None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源论文搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `sources` | `list[str] \| None` | `["openalex", "semantic_scholar", "crossref", "arxiv", "dblp"]` | 数据源列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `search_patents(query, sources=None, per_page=10, **kwargs)` → `list[SearchResponse]`

并发多源专利搜索。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `sources` | `list[str] \| None` | `["patentsview", "pqai"]` | 数据源列表 |
| `per_page` | `int` | `10` | 每个源返回结果数 |

#### `web_search(query, engines=None, max_results_per_engine=10)` → `WebSearchResponse`

并发多引擎网页搜索 + URL 去重。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | `str` | — | 搜索关键词 |
| `engines` | `list[str] \| None` | `["duckduckgo", "yahoo", "brave"]` | 引擎列表 |
| `max_results_per_engine` | `int` | `10` | 每个引擎最大结果数 |

### 配置管理

```python
from souwen import get_config, reload_config
```

#### `get_config()` → `SouWenConfig`

获取全局配置单例（`@lru_cache` 缓存）。

#### `reload_config()` → `SouWenConfig`

清除缓存并重新加载配置。

### PDF 全文获取

```python
from souwen.paper import fetch_pdf
```

#### `fetch_pdf(paper)` → `Path | None`

5 级回退链自动获取论文 PDF：

1. `paper.pdf_url` 直接下载
2. Unpaywall OA 查询
3. CORE 全文查询
4. DOI 重定向解析
5. Sci-Hub 回退

## 数据模型

### PaperResult

```python
class PaperResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    authors: list[Author]           # 作者列表
    abstract: str | None            # 摘要
    doi: str | None                 # DOI
    year: int | None                # 发表年份
    publication_date: date | None   # 发表日期
    journal: str | None             # 期刊
    venue: str | None               # 会议/期刊
    citation_count: int | None      # 引用次数
    open_access_url: str | None     # OA 链接
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    tldr: str | None                # TLDR 摘要（Semantic Scholar）
    raw: dict                       # 原始响应
```

### PatentResult

```python
class PatentResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    patent_id: str                  # 公开号/申请号
    application_number: str | None  # 申请号
    publication_date: date | None   # 公开日
    filing_date: date | None        # 申请日
    applicants: list[Applicant]     # 申请人
    inventors: list[str]            # 发明人
    abstract: str | None            # 摘要
    claims: str | None              # 权利要求
    ipc_codes: list[str]            # IPC 分类号
    cpc_codes: list[str]            # CPC 分类号
    family_id: str | None           # 专利族 ID
    legal_status: str | None        # 法律状态
    pdf_url: str | None             # PDF 链接
    source_url: str                 # 源链接
    raw: dict                       # 原始响应
```

### WebSearchResult

```python
class WebSearchResult(BaseModel):
    source: SourceType              # 数据来源
    title: str                      # 标题
    url: str                        # 链接
    snippet: str                    # 摘要片段
    engine: str                     # 搜索引擎名
    raw: dict                       # 原始响应
```

### SearchResponse

```python
class SearchResponse(BaseModel):
    query: str                      # 搜索词
    source: SourceType              # 数据来源
    total_results: int | None       # 总结果数
    results: list[PaperResult] | list[PatentResult] | list[WebSearchResult]
    page: int = 1                   # 当前页
    per_page: int = 10              # 每页数量
```

### Author / Applicant

```python
class Author(BaseModel):
    name: str
    affiliation: str | None = None
    orcid: str | None = None

class Applicant(BaseModel):
    name: str
    country: str | None = None
```

## CLI 命令

### 搜索

```bash
# 论文搜索
souwen search paper <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 专利搜索
souwen search patent <query> [--sources/-s SRC1,SRC2] [--limit/-n 5] [--json/-j]

# 网页搜索
souwen search web <query> [--engines/-e ENG1,ENG2] [--limit/-n 10] [--json/-j]
```

输出格式：
- 默认：Rich 表格（论文显示 Title/Year/Citations/DOI/Source）
- `--json`：JSON 格式（适合管道处理，如 `| jq '.[]'`）

### 配置

```bash
souwen config show    # 显示当前配置（API Key 脱敏）
souwen config init    # 生成 souwen.yaml 模板
```

### 数据源

```bash
souwen sources        # 列出所有数据源及其状态
```

### 健康检查

```bash
souwen doctor         # 检查所有数据源可用性
```

### API 服务

```bash
souwen serve [--port 8000]   # 启动 FastAPI 服务
```

启动后可访问：
- `GET /api/v1/search/paper?q=<query>&per_page=5` — 论文搜索
- `GET /api/v1/search/patent?q=<query>&per_page=5` — 专利搜索
- `GET /api/v1/search/web?q=<query>&engines=duckduckgo,brave` — 网页搜索
- `GET /api/v1/sources` — 数据源列表
- `GET /docs` — OpenAPI 文档

## MCP 工具

SouWen 支持 [Model Context Protocol](https://modelcontextprotocol.io/)，可作为 AI Agent 的工具服务。

### 启动

```bash
python -m souwen.integrations.mcp_server
```

需安装 `pip install mcp`。

### 工具列表

#### `search_papers`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | array | `["openalex", "arxiv", "crossref"]` | 数据源 |
| `limit` | int | `5` | 结果数 |

返回：JSON `SearchResponse` 数组

#### `search_patents`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `sources` | array | `["patentsview", "pqai"]` | 数据源 |
| `limit` | int | `5` | 结果数 |

返回：JSON `SearchResponse` 数组

#### `web_search`

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | — | 搜索关键词 |
| `engines` | array | — | 引擎列表 |
| `limit` | int | `10` | 结果数 |

返回：JSON `SearchResponse` 对象

#### `get_status`

无参数。返回所有数据源的健康状态报告。
