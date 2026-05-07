# Source Catalog

Source Catalog 是 SouWen 的公开数据源契约。它不是手写清单，而是从
`SourceAdapter` registry 派生，保证 CLI、REST API、Panel、doctor 和生成文档
看到同一份事实。

## 公开结构

`/api/v1/sources` 和 `souwen sources --json` 返回：

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
    "paper:search": ["arxiv", "biorxiv", "crossref", "dblp", "openalex", "pubmed"]
  }
}
```

调用方应按 `sources[]` 过滤：

- 用 `domain` 选择业务领域；
- 用 `category` 选择展示分组；
- 用 `capabilities` 选择动作；
- 用 `available` 判断当前配置下是否可直接调用；
- 用 `credentials_satisfied` 和 `configured_credentials` 区分缺凭据和已配置凭据。

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
凭据源、自建实例未配置源仍保留 catalog 条目，但 `available=false`。

完整数据源表见 [data-sources.md](./data-sources.md)。新增源流程见
[adding-a-source.md](./adding-a-source.md)。
