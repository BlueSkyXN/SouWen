# 外观定制

> SouWen 管理面板的外观系统：皮肤、明暗模式、配色方案

## 概览

SouWen 的管理面板（`/panel`）采用三层外观体系：

| 层级 | 名称 | 切换方式 | 说明 |
|------|------|----------|------|
| 🎭 **皮肤 Skin** | 整体 UI 风格 | 构建时 或 运行时 | 完全不同的布局、组件、路由、交互逻辑 |
| 🌓 **模式 Mode** | 明暗模式 | 运行时 | Light / Dark |
| 🎨 **配色 Scheme** | 强调色方案 | 运行时 | 每个皮肤定义自己支持的配色集 |

> 默认 UI 语言为简体中文（完整 i18n 词表位于 `panel/src/core/i18n/zh-CN.json`），所有皮肤均接入 i18next，新增页面/组件请通过 `t('xxx')` 引用 key，避免硬编码文案。

## 可用皮肤

当前内置 4 个皮肤：`souwen-classic`、`carbon`、`apple`、`ios`。

### souwen-classic（默认）

经典风格，参照 Apple/Google 设计语言，追求优雅简洁。

- **设计理念**：把复杂藏在优雅背后，Apple HIG 的克制与质感 + Material Design 3 的层级感
- **视觉特征**：大圆角卡片、柔和弥散阴影、毛玻璃效果、Framer Motion 动效
- **布局**：左侧渐变导航栏 + 顶部标题栏 + 主内容区
- **配色方案**：星云 Nebula（靛蓝紫）、极光 Aurora（青碧绿）、黑曜石 Obsidian（石板灰）

#### 包含页面

| 页面 | 功能 |
|------|------|
| **搜索页** | Command Center 布局：居中搜索框、分段控制器（论文/专利/网页）、建议标签、渐变光球背景 |
| **仪表盘** | 紧凑统计卡（compact stats）、健康环形图、数据源状态概览 |
| **数据源页** | 分组卡片展示 + 顶部 Filter Tabs（按域/状态过滤），左边框按状态区分，卡片顶部显示集成类型色带（按 integration_type 区分 open_api / scraper / official_api / self_hosted） |
| **配置页** | 分组折叠面板，API Key 管理，顶部彩色边框 |
| **登录页** | 居中卡片，无密码时自动登录 |
| **抓取页** | 批量 URL 输入框、提供者选择、超时滑块、可折叠结果卡片、Markdown 预览 + 复制/下载 |

> **v0.6.3 视觉升级**：classic 皮肤整体提升美学密度——更细腻的多层阴影 + 强调色辉光（glow）、卡片/导航的毛玻璃（backdrop-filter）、统一的过渡曲线、按钮与卡片的 hover 抬升与色彩反馈、Sources 页 Filter Tabs 与集成类型色带、Dashboard 紧凑统计区。

### carbon

终端/黑客风格，工业感与极客美学。

- **设计理念**：暗色系终端美学，受 Linear、Vercel 等现代开发者工具启发
- **视觉特征**：等宽字体贯穿全局、零圆角（sharp corners）、网格背景、大写下划线命名
- **布局**：顶部全宽导航栏（与 classic 的侧边栏完全不同）
- **配色方案**：终端 Terminal（蓝色 #3b82f6）、矩阵 Matrix（绿色 #10b981）、余烬 Ember（琥珀 #f59e0b）

### apple

Apple HIG 灵感皮肤，强调克制、留白与系统感。

- **设计理念**：参照 macOS / Apple 官网的视觉语言，干净的字体层级与中性背景，强调内容本身
- **视觉特征**：精致的阴影与分割线、SF 风格的字号节奏、温和的交互反馈
- **配色方案**（详见 `panel/src/skins/apple/skin.config.ts`）：
  - **Apple Blue**（默认 `blue`）：Apple 品牌蓝 `#0071e3`

### ios

macOS Settings / iOS 设置面板灵感皮肤，强调分组列表与系统原生感。

- **设计理念**：模仿 macOS 系统设置的 sidebar + grouped list 结构，强调信息层级与一致的图标语言
- **视觉特征**：系统色调、分组卡片、列表行内分隔线、原生风格控件
- **配色方案**（详见 `panel/src/skins/ios/skin.config.ts`）：
  - **iOS Default**（默认 `default`）：iOS 系统蓝 `#007aff`

## 配色方案

每个皮肤定义自己的配色方案集合，用户在运行时切换。

### souwen-classic 配色方案

### 🌌 星云 Nebula（默认）

靛蓝紫色系，沉稳专业。

| 属性 | 浅色模式 | 深色模式 |
|------|----------|----------|
| 主强调色 | `#4f46e5` (靛蓝) | `#818cf8` (浅靛蓝) |
| 次强调色 | `#7c3aed` (紫罗兰) | `#a78bfa` (浅紫) |
| 渐变方向 | 靛蓝 → 紫罗兰 → 靛蓝 | 靛蓝 → 紫 → 浅靛蓝 |
| 适合场景 | 学术研究、正式场景 | — |

### 🌊 极光 Aurora

青碧绿色系，清新自然。

| 属性 | 浅色模式 | 深色模式 |
|------|----------|----------|
| 主强调色 | `#0d9488` (青绿) | `#2dd4bf` (浅青绿) |
| 次强调色 | `#06b6d4` (青) | `#22d3ee` (浅青) |
| 渐变方向 | 青绿 → 青 → 翠绿 | 翠绿 → 浅青 → 浅青绿 |
| 适合场景 | 长时间阅读、护眼 | — |

### 🖤 黑曜石 Obsidian

石板灰色系，极简克制。

| 属性 | 浅色模式 | 深色模式 |
|------|----------|----------|
| 主强调色 | `#475569` (石板灰) | `#94a3b8` (浅石板灰) |
| 次强调色 | `#64748b` (蓝灰) | `#cbd5e1` (浅蓝灰) |
| 渐变方向 | 石板灰 → 蓝灰 → 暗石板 | 浅石板 → 浅蓝灰 → 浅石板灰 |
| 适合场景 | 极简审美、减少干扰 | — |

### apple 配色方案

| 方案 | id | 强调色 | 备注 |
|------|----|--------|------|
| Apple Blue（默认） | `blue` | `#0071e3` | Apple 品牌蓝 |

### ios 配色方案

| 方案 | id | 强调色 | 备注 |
|------|----|--------|------|
| iOS Default（默认） | `default` | `#007aff` | iOS 系统蓝 |

### carbon 配色方案

Carbon 皮肤提供 3 种配色方案，支持明暗两种模式：

- **暗色模式**（默认）：经典暗色终端背景
- **浅色模式**：白色背景、深色文字，保留等宽字体和零圆角设计语言

#### 💠 终端 Terminal（默认）

经典蓝色终端风格。

| 属性 | 值 |
|------|-----|
| 强调色 | `#3b82f6` (蓝色) |
| 悬停色 | `#2563eb` (深蓝) |

#### 🟢 矩阵 Matrix

绿色黑客风格，致敬 Matrix。

| 属性 | 值 |
|------|-----|
| 强调色 | `#10b981` (翠绿) |
| 悬停色 | `#059669` (深翠绿) |

#### 🔥 余烬 Ember

琥珀暖色风格，温暖而有力。

| 属性 | 值 |
|------|-----|
| 强调色 | `#f59e0b` (琥珀) |
| 悬停色 | `#d97706` (深琥珀) |

## 如何切换

### 配色方案 & 明暗模式（运行时）

在管理面板右上角的标题栏中：

- **明暗模式**：点击 ☀️/🌙 图标切换
- **配色方案**：点击调色盘 🎨 图标，从下拉菜单选择
- **皮肤切换**：点击「切换皮肤」按钮，从下拉面板选择（多皮肤构建时可用）

下拉面板支持：
- 点击外部区域自动关闭
- 按 Escape 键关闭
- 无障碍属性（`aria-expanded`、`aria-haspopup`）

选择会自动保存到浏览器的 localStorage，下次访问时自动恢复。

### 皮肤切换（运行时 + 构建时）

皮肤支持两种切换方式：

#### 运行时切换（多皮肤构建）

当使用 `VITE_SKINS=all` 或 `VITE_SKINS=souwen-classic,carbon,apple,ios` 等多皮肤值构建时，面板会在标题栏显示「切换皮肤」按钮。
Docker 构建默认包含所有皮肤（`souwen-classic` / `carbon` / `apple` / `ios`），开箱即支持运行时切换。

切换皮肤后页面会自动刷新，选择保存在 localStorage 中。

#### 构建时选择（单皮肤构建）

使用 `VITE_SKINS=souwen-classic` 构建时，仅包含指定皮肤，体积更小，不显示切换按钮。

#### 方式一：本地开发

```bash
cd panel

# 默认开发（全皮肤，可运行时切换）
npm run dev

# 单皮肤开发（仅 classic / carbon 提供了快捷脚本）
npm run dev:classic            # 仅 classic
npm run dev:carbon             # 仅 carbon

# apple / ios 没有专用脚本，请直接通过 VITE_SKINS 指定
VITE_SKINS=apple npm run dev
VITE_SKINS=ios npm run dev

# 任意组合
VITE_SKINS=souwen-classic,apple npm run dev

# 全皮肤开发（等同于默认 dev）
npm run dev:all
```

#### 方式二：本地构建

```bash
cd panel

# 默认构建（全皮肤）
npm run build

# 单皮肤构建（体积更小，仅 classic / carbon 提供快捷脚本）
npm run build:classic
npm run build:carbon

# apple / ios 通过 VITE_SKINS 直接构建
VITE_SKINS=apple npm run build
VITE_SKINS=ios npm run build

# 全皮肤构建（等同于默认 build）
npm run build:all

# 构建流程会自动：
# 1. TypeScript 类型检查（tsc -b）
# 2. Vite 打包为单文件 dist/index.html
# 3. 复制到 src/souwen/server/panel.html
```

#### 方式三：Docker 构建

Docker 构建默认包含所有皮肤，可通过 `SKINS` 构建参数覆盖：

```bash
# 默认全皮肤
docker build -t souwen .

# 仅 classic 皮肤（体积更小）
docker build --build-arg SKINS=souwen-classic -t souwen .

docker compose up -d
```

#### 环境变量速查表

| 环境/场景 | 变量名 | 设置方式 | 示例 |
|-----------|--------|----------|------|
| 本地 npm 开发 | `VITE_SKINS` | Shell 环境变量 | `VITE_SKINS=all npm run dev` |
| 本地 npm 构建 | `VITE_SKINS` | Shell 环境变量 | `VITE_SKINS=all npm run build` |
| npm 快捷脚本 | — | package.json scripts | `npm run dev:all` / `npm run build:all` |
| Docker build | `SKINS` | `--build-arg` | `docker build --build-arg SKINS=souwen-classic .` |

#### 原理说明

`vite.config.ts` 通过 `VITE_SKINS` 环境变量控制 Vite 虚拟模块 `virtual:skin-loader`：

- **单皮肤模式**：仅导入一个皮肤的 CSS 和组件
- **多皮肤模式**：导入所有指定皮肤，通过 `html[data-skin]` CSS 选择器隔离样式

`main.tsx` 在 React 渲染前同步设置 `data-skin`、`data-mode`、`data-scheme` 属性，避免无样式闪烁。

## 创建自定义皮肤

想要完全不同的 UI？可以创建自己的皮肤：

### 1. 复制模板

```bash
cp -r panel/src/skins/souwen-classic panel/src/skins/my-skin
```

### 2. 修改皮肤配置

编辑 `panel/src/skins/my-skin/skin.config.ts`：

```typescript
export const skinConfig: SkinConfig = {
  id: 'my-skin',
  labelKey: 'skin.mySkin',
  descriptionKey: 'skin.mySkinDesc',
  defaultScheme: 'nebula',
  defaultMode: 'light',  // 默认明暗模式
  schemes: [
    // 可以定义自己的配色方案，也可以复用现有的
    { id: 'nebula', labelKey: 'theme.nebula', dotColor: '#4f46e5' },
    { id: 'ocean', labelKey: 'theme.ocean', dotColor: '#0ea5e9' },
  ],
}
```

### 3. 导出必需接口

皮肤的 `index.ts` 必须导出以下内容：

```typescript
export { MainLayout as AppShell } from './components/layout/MainLayout'
export { LoginPage } from './pages/LoginPage'
export { skinRoutes } from './routes'
export { skinConfig } from './skin.config'
export { ErrorBoundary } from './components/common/ErrorBoundary'
export { ToastContainer } from './components/common/Toast'
export { Spinner } from './components/common/Spinner'

import { useSkinStore } from './stores/skinStore'
export function bootstrap() {
  useSkinStore.getState().loadSkin()
}
```

### 4. CSS 命名空间

`styles/global.scss` 中所有选择器必须使用 `html[data-skin='my-skin']` 命名空间：

```scss
html[data-skin='my-skin'] {
  --bg: #ffffff;
  --text: #1a1a1a;
  // ...
}

html[data-skin='my-skin'][data-mode='dark'] {
  --bg: #0a0a0a;
  --text: #e5e5e5;
}
```

### 5. 注册到构建系统

在 `panel/vite.config.ts` 的 `ALL_SKINS` 数组中添加你的皮肤 ID：

```typescript
const ALL_SKINS = ['souwen-classic', 'carbon', 'apple', 'ios', 'my-skin']
```

### 5. 构建并测试

```bash
# 单皮肤开发
VITE_SKINS=my-skin npm run dev

# 多皮肤开发（与其他皮肤一起）
VITE_SKINS=souwen-classic,my-skin npm run dev

# 构建
VITE_SKINS=my-skin npm run build
```

## 共享 vs 独立

| 跨皮肤共享（core/） | 皮肤独立（skins/xxx/） |
|---|---|
| 认证状态（authStore） | 所有 UI 组件 |
| 通知系统（notificationStore） | 页面布局 |
| API 客户端 | SCSS 样式 |
| TypeScript 类型 | 路由定义 |
| 国际化翻译 | 皮肤状态（明暗/配色） |
| 工具函数（动画、归一化） | 皮肤配置 |

皮肤可以通过 `@core/...` 路径引用任何共享模块：

```typescript
import { useAuthStore } from '@core/stores/authStore'
import { api } from '@core/services/api'
import type { SearchResult } from '@core/types'
```

## 技术细节

### CSS 变量体系

所有视觉属性通过 CSS 自定义属性控制，使用 `html[data-skin]` 进行皮肤级隔离：

```css
/* 皮肤级隔离 —— 每个皮肤的变量仅在自己的 data-skin 下生效 */
html[data-skin='souwen-classic']                         { --bg: #f8f9fb; }
html[data-skin='souwen-classic'][data-mode='dark']       { --bg: #0a0a0f; }
html[data-skin='souwen-classic'][data-scheme='aurora']   { --accent: #0d9488; }

html[data-skin='carbon']                                 { --bg: #0a0a0a; }
html[data-skin='carbon'][data-scheme='matrix']           { --accent: #10b981; }

html[data-skin='apple'][data-scheme='blue']              { --accent: #0071e3; }
html[data-skin='ios'][data-scheme='default']             { --accent: #007aff; }
```

### Skin Registry

皮肤通过 `registerSkin()` 注册到运行时注册表。`main.tsx` 在 `createRoot()` 之前同步完成：

1. 导入 `virtual:skin-loader`（注册所有构建的皮肤）
2. 从 localStorage 读取用户选择的皮肤
3. 调用 `getSkinOrDefault()` 获取有效皮肤（无效 ID 自动回退）
4. 同步设置 `data-skin`、`data-mode`、`data-scheme` 属性
5. 渲染 React 应用

### localStorage 键

| 键名 | 值 | 说明 |
|------|-----|------|
| `souwen_skin` | `souwen-classic` / `carbon` / `apple` / `ios` | 当前皮肤（多皮肤模式） |
| `souwen_mode` | `light` / `dark` | 明暗模式 |
| `souwen_scheme` | classic：`nebula` / `aurora` / `obsidian`<br>carbon：`terminal` / `matrix` / `ember`<br>apple：`blue`<br>ios：`default` | 配色方案（按当前皮肤可选值取值） |

> 向后兼容：旧版 `souwen_theme` 和 `souwen_visual_theme` 键会在加载时自动迁移。
