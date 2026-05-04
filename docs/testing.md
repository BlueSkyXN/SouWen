# 测试策略

SouWen 的测试体系分成两层：

- **本地确定性测试**：默认 `pytest`，用于验证代码契约、配置、registry、parser、mock integration 和接口结构。
- **云端真实能力测试**：独立 `scripts/*_functional_check.py` 或 `scripts/*_smoke.py`，用于验证真实包、浏览器运行时、外部服务和部署环境。

这个分层的目标是让本地开发反馈保持稳定，同时让 CI 能发现 mock 测试覆盖不到的真实运行问题。

## 本地确定性测试

默认本地测试不应依赖真实互联网、浏览器运行时、真实 API key 或云端服务。

适合留在 `pytest` 的内容：

- schema / model validation。
- config merge、环境变量解析和凭据字段解析。
- registry / source catalog 一致性。
- provider 注册、handler 注册和参数传递。
- parser 对固定响应的处理。
- HTTP error mapping、timeout、retry、rate limit 行为。
- 使用 `pytest-httpx`、monkeypatch 或本地 fixture 的 mock integration。
- FastAPI route 参数校验和响应结构。

推荐本地命令：

```bash
PYTHONPATH=src python3 -m pytest -q
python3 -m ruff check src/ tests/ scripts/
python3 -m ruff format --check src/ tests/ scripts/
```

## 云端真实能力测试

真实外部能力应放在专项脚本中，并由 GitHub Actions 专项 job 执行。

适合专项脚本的内容：

- Playwright / Patchright / Crawl4AI / Scrapling 等 browser runtime。
- 真实第三方 Python 包安装、import 和最小调用。
- 真实外部网站抓取或动态渲染抓取。
- Hugging Face Space live endpoint / post-deploy smoke。
- 需要 API key、代理、WARP、自建 URL 的 provider。
- 外部插件真实安装和 entry point discovery。

专项脚本必须独立运行，不依赖 pytest fixture。运行时安装行为应在 workflow step 中显式呈现，不应隐藏在 Python 脚本里。

## Outcome 语义

所有专项脚本使用统一 Outcome。

| Outcome | 语义 | 退出码影响 |
|---|---|---|
| `PASS` | required check 全部通过 | 0 |
| `WARN` | 非 required check 失败或退化 | 0 |
| `FAIL` | required check 失败，核心契约破裂 | 1 |
| `SKIP` | 缺少 secret、runtime 或显式跳过 | 0 |

`FAIL` 示例：

- import 失败。
- provider 注册失败。
- required 字段缺失或解析失败。
- SSRF guard / URL allowlist / credential guard 没生效。
- required endpoint 返回非预期结构。
- browser runtime 已安装但启动失败。

`WARN` 示例：

- 非关键外部源单次网络波动。
- 可选字段缺失。
- 性能退化但未超过硬超时。
- 外部服务短暂 429，但核心 fixture 和 required check 正常。

`SKIP` 示例：

- 缺少 required secret。
- 显式 `--mode offline`。
- fork PR 不允许访问 Environment secret。
- runtime 未安装，且当前 job 不负责安装。

## Report 规则

专项脚本必须支持 JSON report 和 Markdown report：

```bash
python scripts/<name>_functional_check.py \
  --mode fixture \
  --timeout 30 \
  --json-report artifacts/<name>.json \
  --markdown-report artifacts/<name>.md
```

JSON report 是 source of truth，Markdown 只作为人类可读渲染。CI 应上传 report artifact，方便排障和后续趋势分析。

## CI 分级

| 层级 | 运行时机 | 适用内容 |
|---|---|---|
| PR required | pull request | 稳定、低成本、关键外部能力 smoke |
| Nightly / manual | schedule / workflow_dispatch | 高波动真实外部源、secret-backed provider |
| Release gate | tag / release branch / manual | 发版前完整重型外部能力集合 |

PR required 只覆盖关键最小 smoke。高波动外部源不应默认阻断每个 PR，但 nightly/manual 失败必须能被追踪，不能静默遗忘。

## 当前专项矩阵

| 能力 | 层级 | pytest 保留内容 | 专项脚本覆盖 | CI job |
|---|---|---|---|---|
| Scrapling | PR required | provider 注册、配置解析、fixture/mock 契约 | 真实 `scrapling.fetchers` import、本地 fixture 抓取、browser dynamic 抓取 | `Scrapling 云端功能测试` |
| Crawl4AI | PR required | handler 注册、参数派发、错误聚合契约 | 真实 `crawl4ai.AsyncWebCrawler` import、本地 fixture browser 抓取、缺 runtime 时 SKIP/FAIL 分级 | `Crawl4AI 云端功能测试` |
| Plugin entry point | PR required | 插件契约、loader、manager、handler 注册的 mock/monkeypatch 单测 | 真实 `pip install -e examples/minimal-plugin`、entry point discovery、registry/plugin manager/fetch handler 视图、可选 `superweb2pdf` WARN | `插件云端功能测试` |
| HF Space smoke | deploy smoke / release gate | `hf_space_smoke` 参数、矩阵覆盖和 report 渲染的确定性单测 | 部署后 surface/capability smoke、统一 JSON Outcome report、Markdown 排障报告 | `HF Space CD` |

## Secrets 边界

需要 API key、账号、代理或自建服务 URL 的专项测试必须挂 GitHub Environment。fork PR 默认不运行 secret-backed smoke。

默认权限：

```yaml
permissions:
  contents: read
```

只有自动创建 issue 或发布评论的 workflow 才增加写权限。
