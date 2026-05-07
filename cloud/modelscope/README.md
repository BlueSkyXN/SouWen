# SouWen 搜文 — 学术搜索 API

面向 AI Agent 的学术论文 + 专利 + 网页统一搜索 API 服务。

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 存活探针 |
| GET | `/readiness` | 就绪探针（v0.6.1） |
| GET | `/api/v1/search/paper?q=...` | 搜索学术论文 |
| GET | `/api/v1/search/patent?q=...` | 搜索专利 |
| GET | `/api/v1/search/web?q=...` | 搜索网页（默认 `engines=duckduckgo,bing`） |
| GET | `/api/v1/sources` | 列出所有可用数据源 |
| GET | `/api/v1/admin/config` | 查看配置（需认证） |
| POST | `/api/v1/admin/config/reload` | 重载配置（需认证） |
| GET | `/api/v1/admin/doctor` | 数据源健康检查（需认证） |
| GET | `/api/v1/admin/warp` | 查询 WARP 状态（需认证） |
| POST | `/api/v1/admin/warp/enable` | 启用 WARP 代理（需认证） |
| POST | `/api/v1/admin/warp/disable` | 关闭 WARP 代理（需认证） |

## 配置

通过 ModelScope 创空间的**环境变量**注入：

| 变量 | 说明 |
|------|------|
| `SOUWEN_CONFIG_B64` | Base64 编码的 souwen.yaml 完整配置 |
| `SOUWEN_USER_PASSWORD` | 用户密码，保护搜索和 `/api/v1/sources` |
| `SOUWEN_ADMIN_PASSWORD` | 管理密码，保护 `/api/v1/admin/*` |
| `SOUWEN_GUEST_ENABLED` | 设为 `true` 时允许无 Token 访问搜索端点 |
| `SOUWEN_ADMIN_OPEN` | 设为 `1` 时显式放行未配置密码的 admin 端点（仅本地/CI 调试用） |
| `SOUWEN_TRUSTED_PROXIES` | 受信反向代理 IP/CIDR 列表，逗号分隔 |
| `SOUWEN_EXPOSE_DOCS` | 是否暴露 `/docs`、`/redoc`、`/openapi.json`，生产建议 `false` |
| `SOUWEN_MAX_CONCURRENCY` | 聚合搜索并发上限，默认 `10`（v0.6.0） |
| `SOUWEN_OPENALEX_EMAIL` | OpenAlex 邮箱（免费，提升速率） |
| `SOUWEN_TAVILY_API_KEY` | Tavily AI 搜索 Key |
| `WARP_ENABLED` | 设为 `1` 启用内嵌 Cloudflare WARP 代理 |
| ... | 其他 SOUWEN_* 环境变量均可直接设置 |

> 大部分爬虫引擎（DuckDuckGo、Yahoo 等）无需 API Key 即可使用。

## ModelScope 部署说明

- **端口固定 7860**：ModelScope 创空间要求容器监听 `7860`，镜像内已通过 `ENV PORT=7860` 固定，请勿覆盖。
- **GitHub 加速**：构建镜像时可通过 `--build-arg GH_PROXY=https://ghproxy.com` 为 `wgcf` / `wireproxy` 等 GitHub Releases 下载注入代理前缀，规避 ModelScope 构建机访问 GitHub 的网络限制。详见 `cloud/modelscope/Dockerfile`。

## 源码

- 项目仓库：<https://github.com/BlueSkyXN/SouWen>
