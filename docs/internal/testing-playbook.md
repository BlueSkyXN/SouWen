# 外部能力测试迁移 Playbook

每迁移一个 provider、runtime 或部署 smoke，都按这份 checklist 执行。

## 1. 定位测试层级

- [ ] 确认哪些行为留在 `pytest`。
- [ ] 确认哪些行为进入专项脚本。
- [ ] 确认该专项脚本属于 PR required、nightly/manual 还是 release gate。

保留在 `pytest` 的内容：

- config / registry / parser / error mapping。
- mock response 处理。
- provider 或 handler 注册。
- FastAPI route 参数和响应结构。

迁移到专项脚本的内容：

- 真实 package 安装或 import。
- browser runtime 启动。
- 真实外部 endpoint 调用。
- secret-backed provider smoke。
- post-deploy live smoke。

## 2. 新增或改造专项脚本

- [ ] 文件命名为 `scripts/<name>_functional_check.py` 或 `scripts/<name>_smoke.py`。
- [ ] 使用 `scripts/_functional_common.py`。
- [ ] 支持 `--mode`、`--timeout`、`--json-report`、`--markdown-report`。
- [ ] 明确 required check 和 warn-only check。
- [ ] JSON report 作为 source of truth。
- [ ] Markdown report 只由 JSON 同源结构渲染。
- [ ] 脚本能脱离 pytest 独立运行。
- [ ] 不在脚本中偷偷安装 runtime。

## 3. 更新 CI

- [ ] job 名称能清楚表达外部能力边界。
- [ ] job 使用 `needs: lint`。
- [ ] job 添加 `timeout-minutes`。
- [ ] 重型 job 添加 concurrency。
- [ ] browser / runtime job 添加 cache。
- [ ] job 上传 JSON 和 Markdown artifact。
- [ ] `push.paths` 或 changes gate 覆盖相关源码、脚本、依赖文件和 workflow。
- [ ] secret-backed job 挂 GitHub Environment。
- [ ] fork PR 不运行 secret-backed job。
- [ ] 外部 live 验证使用当前保留的 workflow 或经明确批准的手动路径。

## 4. 更新文档

- [ ] 在 `docs/testing.md` 中补充该能力的测试层级。
- [ ] 如果新增 Environment secret，在对应部署或配置文档中说明变量名和用途。
- [ ] 如果该 job 是 nightly/manual，说明失败追踪方式。

## 5. 验收

- [ ] 默认 `pytest` 不因缺少 runtime、secret 或真实网络失败。
- [ ] 专项脚本 fixture/offline 模式能本地运行。
- [ ] CI artifact 中能下载 JSON 和 Markdown report。
- [ ] required failure 会让 job 失败。
- [ ] warn-only failure 不会让 job 失败，但会进入 report。
- [ ] 远端 PR checks 回读确认对应 job 通过。
- [ ] 对 nightly / release gate，确认 schedule / tag / manual 入口不会静默遗忘。

## 6. 发布证据

发布候选的正式门禁以 `.github/workflows/release-candidate.yml` 和
`docs/internal/rc-readiness-gates.md` 为准。外部 provider/runtime 验证只在明确批准的环境中
独立执行，不属于普通 PR 或当前发布 contract。

## 迁移示例：HF Space smoke

HF Space smoke 属于 deploy smoke / release gate：

- pytest 保留 `hf_space_smoke` 的参数解析、矩阵覆盖、Markdown 渲染和 offline report 单测。
- `scripts/hf_space_smoke.py` 继续负责部署后 surface / capability smoke，但 JSON report 对齐统一 `schema_version`、`script`、`mode`、`overall`、`checks` 结构。
- `--json-report` / `--markdown-report` 作为统一 CLI alias，兼容原有 `--json-file` / `--report-file`。
- 本地可用 `--mode offline` 验证 report 写入，不触碰真实 HF Space endpoint。
- `HF Space CD` 上传 surface / capability 两类 JSON + Markdown artifact；JSON 是 source of truth，Markdown 只用于排障阅读。
