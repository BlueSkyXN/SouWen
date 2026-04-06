# SouWen 搜文 — 学术搜索 API

面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API 服务。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/v1/search/paper?q=...` | 搜索学术论文 |
| GET | `/api/v1/search/patent?q=...` | 搜索专利 |
| GET | `/api/v1/search/web?q=...` | 搜索网页 |
| GET | `/api/v1/sources` | 列出所有可用数据源 |

## 配置

通过 ModelScope 创空间的**环境变量**注入：

| 变量 | 说明 |
|------|------|
| `SOUWEN_CONFIG_B64` | Base64 编码的 souwen.yaml 完整配置 |
| `SOUWEN_OPENALEX_EMAIL` | OpenAlex 邮箱（免费，提升速率） |
| `SOUWEN_TAVILY_API_KEY` | Tavily AI 搜索 Key |
| ... | 其他 SOUWEN_* 环境变量均可直接设置 |

> 大部分爬虫引擎（DuckDuckGo、Yahoo 等）无需 API Key 即可使用。

## 源码

- 项目仓库：<https://github.com/SkywalkerSpace/SouWen>
