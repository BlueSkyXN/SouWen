# Panel Appearance Guide

本文档是 SouWen Panel 的本地视觉与交互约束卡片，供修改 `panel/`
或 `panel/src/skins/` 前快速对齐。它记录当前实现的事实，不替代组件源码。

## Architecture

- `panel/src/core/styles/base.scss` 只放共享 reset、focus ring、scrollbar、
  reduced-motion、shared keyframes 和 `.srOnly`。
- 共享行为、service、hook、store、type、i18n 放在 `panel/src/core/`。
- 皮肤 UI、layout、page、route、style 放在 `panel/src/skins/<skin>/`。
- 皮肤不能互相 import；跨皮肤逻辑应上移到 `@core`。
- 样式使用 SCSS Modules 或 `html[data-skin='<id>']` 作用域变量；不要新增
  Tailwind 或全局裸选择器。

## Skins

当前 `vite.config.ts` 注册的 skin：

- `souwen-google`：默认 scheme `google`，支持 `google`、`aurora`、`obsidian`。
- `souwen-nebula`：默认 scheme `nebula`，支持 `nebula`、`aurora`、`obsidian`。
- `carbon`：默认 scheme `terminal`，支持 `terminal`、`matrix`、`ember`。
- `apple`：默认 scheme `blue`，Apple-style light-first layout。
- `ios`：默认 scheme `default`，iOS settings-style grouped layout。

每个 skin 必须导出完整 `SkinModule`：`AppShell`、`LoginPage`、`skinRoutes`、
`skinConfig`、`ErrorBoundary`、`ToastContainer`、`Spinner`、`bootstrap`。

## Design Tokens

优先使用已有 CSS variables，而不是在页面里硬编码颜色、阴影或半径。
常见 token 包括：

- Color: `--bg`、`--bg-card`、`--bg-input`、`--bg-hover`、`--text`、
  `--text-secondary`、`--text-muted`、`--border`、`--border-strong`。
- Accent: `--accent`、`--accent-hover`、`--accent-light`、`--accent-glow`，
  Google/Nebula 还保留 `--primary` 系列兼容 token。
- Semantic: `--success`、`--success-light`、`--warning`、`--warning-light`、
  `--error`、`--error-light`。
- Layout: `--sidebar-w`、`--header-h`、`--nav-h`、`--content-pad`、
  `--content-max`。
- Radius/shadow/transition：优先使用对应 skin 的 `--radius*`、`--shadow*`、
  `--transition*`。

新增 token 时要在相关 skin 的 `styles/global.scss` 中定义，并检查 light/dark
或 scheme 覆盖是否需要同步。

## Interaction

- 表单控件使用 `label` + stable `id`；按钮使用明确 `type`。
- destructive、admin、secret、proxy、base URL 相关操作要保留确认、禁用态、
  loading 态和错误反馈。
- 搜索、抓取、视频等长请求必须保留 AbortController / loading / retry / empty
  state，不要只做 happy path。
- secret 或 redacted display placeholder 不能被原样提交回后端。
- 外部链接使用 `target="_blank"` 时必须带 `rel="noopener noreferrer"`。
- 图标优先使用 `lucide-react`，按钮/工具类操作优先 icon + accessible label。

## Layout

- 工具型页面优先使用紧凑、可扫描、可重复操作的布局。
- 不要把 page section 包成嵌套 card；card 用于结果项、配置项、modal 或
  明确的工具框。
- 控件行、tab、toolbar 在移动端必须可换行或收缩，不能制造水平溢出。
- 固定格式元素要用稳定尺寸、`min/max`、`grid` 或 `aspect-ratio` 约束，避免
  loading、hover、长文案造成布局跳动。
- 不使用 decorative orb、bokeh blob 或无信息量的大渐变背景。

## I18n

- 用户可见文案放在 `panel/src/core/i18n/zh-CN.json`。
- 新增静态 `t('...')` key 后必须补中文翻译。
- `panel/src/core/test/i18n.test.ts` 会扫描静态 `t('...')` 调用并断言
  `zh-CN.json` 已覆盖。
- 动态 key（例如 `t(\`sourceConfig.proxy${...}\`)`）要确保所有实际值在
  `zh-CN.json` 中存在。

## Validation

按改动范围选择最小充分验证：

- Core hook/service/i18n/type：`cd panel && npm test`，并跑相关单测。
- Page 或 skin UI：`cd panel && npm test`、`cd panel && npm run build`。
- Embedded artifact：`cd panel && npm run build:local && npm run check:artifact`。
- 有布局风险的 UI 改动：用浏览器 smoke 检查 desktop 和 mobile viewport，
  确认没有水平溢出、遮挡或空白渲染。
