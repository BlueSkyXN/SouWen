# Source Catalog

Source Catalog 是 SouWen 的公开数据源契约。它不是手写清单，而是从
`SourceAdapter` registry 派生，保证 CLI、REST API、Panel、doctor 和生成文档
看到同一份事实。

## 公开结构

`/api/v1/sources` 返回：

```json
{
  "sources": [
    {
      "name": "arxiv",
      "domain": "paper",
      "category": "paper",
      "capabilities": ["search"],
      "credentials_satisfied": true,
      "configured_credentials": false,
      "runtime_available": true,
      "runtime_reason": "",
      "available": true
    }
  ],
  "categories": [
    {
      "key": "paper",
      "label": "学术论文",
      "order": 10
    }
  ],
  "defaults": {
    "paper:search": ["openalex", "crossref", "arxiv", "dblp", "pubmed", "biorxiv"]
  }
}
```

调用方应按 `sources[]` 过滤：

- 用 `domain` 选择业务领域；
- 用 `category` 选择展示分组；
- 用 `capabilities` 选择动作；
- 用 `available` 判断启用、配置、凭据、本地 runtime 与静态数据条件形成的最终调度 readiness；
- 用 `runtime_available` / `runtime_reason` 诊断当前进程能否加载实现和 optional dependency；
- 用 `data_available` / `data_reason` 诊断本地 catalog 等静态数据前置条件；
- 用 `credentials_satisfied` 和 `configured_credentials` 区分缺凭据和已配置凭据。

`available=true` 表示本地静态条件全部满足，但不证明上游实时可达；只有显式
`live=true` probe 才是带时间戳的外部观测。

## 分类

| Category | 用途 |
|---|---|
| `paper` | 学术论文 |
| `patent` | 专利 |
| `web_general` | 通用网页搜索 |
| `web_professional` | 专业网页搜索、AI 搜索、商业聚合搜索 |
| `social` | 社交平台 |
| `office` | 企业/办公 |
| `developer` | 开发者社区 |
| `knowledge` | 百科/知识库 |
| `cn_tech` | 中文技术社区 |
| `video` | 视频平台 |
| `archive` | 档案/历史 |
| `fetch` | 内容抓取 |

## 与运行时配置的关系

Source Catalog 描述公开源事实；频道配置描述运行时开关和凭据。禁用源、缺必需
凭据源、自建实例未配置源仍保留 catalog 条目，但 `available=false`。Catalog 不承担
live upstream probe；它把 optional package importability 放在独立 runtime 字段中，调用方
不能把静态 `available` 或本地 `runtime_available` 任一字段单独当作 live readiness。

完整数据源表见 [data-sources.md](./data-sources.md)。新增源流程见
[adding-a-source.md](./adding-a-source.md)。
