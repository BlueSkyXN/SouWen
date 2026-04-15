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

#### 包含页面

| 页面 | 功能 |
|------|------|
| **搜索页** | Command Center 布局：居中搜索框、分段控制器（论文/专利/网页）、建议标签、渐变光球背景 |
| **仪表盘** | 统计卡片（渐变色边框）、健康环形图、数据源状态概览 |
| **数据源页** | 分组卡片展示，彩色左边框按状态区分，层级徽章 |
| **配置页** | 分组折叠面板，API Key 管理，顶部彩色边框 |
| **登录页** | 居中卡片，无密码时自动登录 |

## 配色方案

souwen-classic 皮肤提供 3 种配色方案，均支持明暗两种模式：

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

## 如何切换

### 配色方案 & 明暗模式（运行时）

在管理面板右上角的标题栏中：

- **明暗模式**：点击 ☀️/🌙 图标切换
- **配色方案**：点击调色盘 🎨 图标，从下拉菜单选择

选择会自动保存到浏览器的 localStorage，下次访问时自动恢复。

### 皮肤（构建时）

皮肤通过 `VITE_SKIN` 环境变量在构建时选择：

```bash
# 本地构建（默认 souwen-classic）
cd panel
npm run build:classic

# 使用其他皮肤构建
VITE_SKIN=my-custom-skin npm run build

# Docker 构建
docker build --build-arg SKIN=souwen-classic -t souwen .

# Docker Compose（修改 docker-compose.yml 中的 SKIN 值）
docker compose up -d --build
```

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
