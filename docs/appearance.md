# 外观定制

> SouWen 管理面板的外观系统：皮肤、明暗模式、配色方案

## 概览

SouWen 的管理面板（`/panel`）采用三层外观体系：

| 层级 | 名称 | 切换方式 | 说明 |
|------|------|----------|------|
| 🎭 **皮肤 Skin** | 整体 UI 风格 | 构建时 | 完全不同的布局、组件、路由、交互逻辑 |
| 🌓 **模式 Mode** | 明暗模式 | 运行时 | Light / Dark |
| 🎨 **配色 Scheme** | 强调色方案 | 运行时 | 每个皮肤定义自己支持的配色集 |

## 可用皮肤

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
| **仪表盘** | 统计卡片（渐变色边框）、健康环形图、数据源状态概览 |
| **数据源页** | 分组卡片展示，彩色左边框按状态区分，层级徽章 |
| **配置页** | 分组折叠面板，API Key 管理，顶部彩色边框 |
| **登录页** | 居中卡片，无密码时自动登录 |

### carbon

终端/黑客风格，工业感与极客美学。

- **设计理念**：暗色系终端美学，受 Linear、Vercel 等现代开发者工具启发
- **视觉特征**：等宽字体贯穿全局、零圆角（sharp corners）、网格背景、大写下划线命名
- **布局**：顶部全宽导航栏（与 classic 的侧边栏完全不同）
- **配色方案**：终端 Terminal（蓝色 #3b82f6）、矩阵 Matrix（绿色 #10b981）、余烬 Ember（琥珀 #f59e0b）

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

### carbon 配色方案

Carbon 皮肤提供 3 种配色方案，均为暗色风格：

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

选择会自动保存到浏览器的 localStorage，下次访问时自动恢复。

### 皮肤切换（构建时）

**皮肤是构建时选项**，通过 `VITE_SKIN` 环境变量指定，不同皮肤会编译出完全不同的前端页面。
构建完成后，产物是一个单文件 `index.html`（由 vite-plugin-singlefile 生成），会被复制到 `src/souwen/server/panel.html` 供后端服务。

#### 方式一：本地开发

```bash
cd panel

# 使用默认皮肤（souwen-classic）
npm run dev                    # 等同于 VITE_SKIN=souwen-classic vite
npm run dev:classic            # 明确指定 classic

# 使用 carbon 皮肤
VITE_SKIN=carbon npm run dev   # 启动 carbon 皮肤的开发服务器
```

#### 方式二：本地构建

```bash
cd panel

# 构建 classic 皮肤（两种写法等价）
npm run build                  # 默认 classic
npm run build:classic          # 等同于 VITE_SKIN=souwen-classic npm run build

# 构建 carbon 皮肤
VITE_SKIN=carbon npm run build

# 构建流程会自动：
# 1. TypeScript 类型检查（tsc -b）
# 2. Vite 打包为单文件 dist/index.html
# 3. 复制到 src/souwen/server/panel.html
```

#### 方式三：Docker 构建

Dockerfile 使用 `ARG SKIN` 在构建阶段选择皮肤：

```bash
# 使用默认皮肤（souwen-classic）
docker build -t souwen .

# 使用 carbon 皮肤
docker build --build-arg SKIN=carbon -t souwen .
```

#### 方式四：Docker Compose

编辑 `docker-compose.yml` 中的 `SKIN` 参数：

```yaml
services:
  souwen:
    build:
      context: .
      args:
        SKIN: carbon    # 改为你想使用的皮肤名
```

然后重新构建：

```bash
docker compose up -d --build
```

> **注意**：云端 Dockerfile 同样支持 `SKIN` 构建参数，见下方。

#### 方式五：HFS（Hugging Face Spaces）部署

HFS 使用 `cloud/hfs/Dockerfile`，通过 Docker 构建参数选择皮肤。

**方法 A：修改 Dockerfile 默认值**

编辑 `cloud/hfs/Dockerfile` 第 3 行：

```dockerfile
ARG SKIN=carbon          # 将 souwen-classic 改为 carbon
```

**方法 B：通过 HFS 环境变量传入**

Hugging Face Spaces 支持在构建阶段传递 Docker 构建参数。在 Space 的 Settings → Repository secrets & variables 中：

1. 添加变量 `SKIN`，值为 `carbon`（或其他皮肤名）
2. 然后在 `Dockerfile` 中使用：

```dockerfile
ARG SKIN=souwen-classic   # 默认值，会被 HFS 传入的值覆盖
```

> HFS 的 Dockerfile 构建时会自动将同名环境变量映射到 `ARG`，无需额外配置。

**方法 C：docker build 命令行**（本地测试 HFS 镜像时）

```bash
docker build -f cloud/hfs/Dockerfile --build-arg SKIN=carbon -t souwen-hfs .
```

#### 方式六：ModelScope 部署

`cloud/modelscope/Dockerfile` 用法与 HFS 完全一致：

```bash
docker build -f cloud/modelscope/Dockerfile --build-arg SKIN=carbon -t souwen-ms .
```

或修改 Dockerfile 中的 `ARG SKIN=souwen-classic` 默认值。

#### 环境变量速查表

| 环境/场景 | 变量名 | 设置方式 | 示例 |
|-----------|--------|----------|------|
| 本地 npm 开发 | `VITE_SKIN` | Shell 环境变量 | `VITE_SKIN=carbon npm run dev` |
| 本地 npm 构建 | `VITE_SKIN` | Shell 环境变量 | `VITE_SKIN=carbon npm run build` |
| npm 快捷脚本 | — | package.json scripts | `npm run dev:carbon` / `npm run build:carbon` |
| Docker build | `SKIN` | `--build-arg` | `docker build --build-arg SKIN=carbon .` |
| Docker Compose | `SKIN` | docker-compose.yml `args` | `SKIN: carbon` |
| HFS | `SKIN` | Dockerfile ARG / Space 变量 | 修改 ARG 默认值或 Space Settings |
| ModelScope | `SKIN` | Dockerfile ARG | 修改 ARG 默认值 |

> **关键区别**：`VITE_SKIN` 是 Vite 构建时使用的环境变量（npm 脚本场景），`SKIN` 是 Docker 构建参数（Dockerfile 场景）。
> Dockerfile 内部会将 `SKIN` 转换为 `VITE_SKIN`：`RUN VITE_SKIN=${SKIN} npm run build`

#### 原理说明

`vite.config.ts` 根据 `VITE_SKIN` 环境变量设置 `@skin` 路径别名：

```typescript
const skin = process.env.VITE_SKIN || 'souwen-classic'

export default defineConfig({
  resolve: {
    alias: {
      '@core': path.resolve(__dirname, 'src/core'),
      '@skin': path.resolve(__dirname, `src/skins/${skin}`),
    },
  },
})
```

`App.tsx` 和 `main.tsx` 通过 `@skin` 导入皮肤的组件（AppShell、LoginPage、routes 等），
因此不同皮肤可以拥有完全不同的布局、组件、路由和交互逻辑，而共享同一套 core 层（认证、API、i18n、类型）。

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
  schemes: [
    // 可以定义自己的配色方案，也可以复用现有的
    { id: 'nebula', labelKey: 'theme.nebula', dotColor: '#4f46e5' },
    { id: 'ocean', labelKey: 'theme.ocean', dotColor: '#0ea5e9' },
  ],
}
```

### 3. 自由修改 UI

皮肤目录下的所有文件都是独立的：

- `components/` — 修改或替换所有 UI 组件
- `pages/` — 重新设计页面布局
- `styles/` — 使用完全不同的设计语言
- `routes.tsx` — 调整路由结构
- `stores/skinStore.ts` — 自定义状态管理逻辑

### 4. 构建并测试

```bash
VITE_SKIN=my-skin npm run dev    # 开发预览
VITE_SKIN=my-skin npm run build  # 构建产物
```

### 5. 提交到 Docker

```bash
docker build --build-arg SKIN=my-skin -t souwen .
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

所有视觉属性通过 CSS 自定义属性控制：

```css
/* 明暗模式通过 data-mode 属性切换 */
:root           { --bg: #f8f9fb; }    /* 浅色 */
[data-mode='dark'] { --bg: #0a0a0f; } /* 深色 */

/* 配色方案通过 data-scheme 属性切换 */
[data-scheme='aurora']    { --accent: #0d9488; }   /* 极光 */
[data-scheme='obsidian']  { --accent: #475569; }   /* 黑曜石 */
/* 默认 nebula 不需要额外选择器 */
```

### localStorage 键

| 键名 | 值 | 说明 |
|------|-----|------|
| `souwen_mode` | `light` / `dark` | 明暗模式 |
| `souwen_scheme` | `nebula` / `aurora` / `obsidian` | 配色方案 |

> 向后兼容：旧版 `souwen_theme` 和 `souwen_visual_theme` 键会在加载时自动迁移。
