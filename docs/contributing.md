# 贡献指南

> 如何为 SouWen 贡献代码

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/BlueSkyXN/SouWen.git
cd SouWen

# 安装开发依赖
pip install -e ".[dev]"

# 安装爬虫可选依赖（TLS 指纹模拟）
pip install -e ".[scraper]"

# 安装 Playwright 浏览器
playwright install chromium
```

## 运行测试

```bash
# 运行全部后端测试
pytest tests/ -v

# 快速运行
pytest tests/ -q --tb=short

# 运行前端测试
cd panel && npm test

# 运行示例脚本
python examples/search_papers.py
python examples/search_patents.py
python examples/search_web.py
```

## 前端开发

管理面板位于 `panel/` 目录，使用 React + TypeScript + SCSS Modules + Framer Motion。

### 环境搭建

```bash
cd panel
npm install
npm run dev              # 启动开发服务器（默认全皮肤，可运行时切换）
npm run dev:classic      # 单皮肤开发
```

### 目录结构

```
panel/src/
  core/                  # 跨皮肤共享（stores, API, types, i18n, skin-registry）
    styles/base.scss     # 共享 CSS 重置
    skin-registry.ts     # 运行时皮肤注册表
  skins/
    souwen-classic/      # 经典皮肤
      components/        # UI 组件（含 ErrorBoundary, Toast, Spinner）
      pages/             # 页面
      styles/            # SCSS 样式（通过 html[data-skin] 命名空间隔离）
      stores/            # 皮肤状态管理
      routes.tsx         # 路由定义
      skin.config.ts     # 皮肤配置（配色方案、默认模式）
      index.ts           # 皮肤入口（导出 SkinModule 接口 + bootstrap）
    carbon/              # 终端风格皮肤
```

### 构建

```bash
npm run build            # 默认全皮肤构建
npm run build:classic    # 单皮肤构建（体积更小）
# 产物：单文件 dist/index.html，自动复制到 src/souwen/server/panel.html
```

### 创建新皮肤

1. 复制 `panel/src/skins/souwen-classic/` 为新目录（如 `skins/my-skin/`）
2. 修改 `skin.config.ts` 中的皮肤元信息和配色方案
3. 确保 `index.ts` 导出完整的 `SkinModule` 接口（含 `bootstrap`、`ErrorBoundary`、`Spinner`）
4. CSS 使用 `html[data-skin='my-skin']` 命名空间
5. 在 `vite.config.ts` 的 `ALL_SKINS` 数组中注册
6. 构建：`VITE_SKINS=my-skin npm run build`

### 注意事项

- 使用 `@core/...` 引用共享模块
- 皮肤之间不可互相引用，只能引用 `@core`
- 动画使用 Framer Motion：导入 `m`（不是 `motion`），`type: 'spring'` 需要 `as const`
- SCSS 变量定义在 `styles/variables.scss`，全局 token 通过 CSS 自定义属性
- 不使用 Tailwind — 项目使用 SCSS Modules + CSS Variables

## 代码风格

- **格式化工具**：[Ruff](https://docs.astral.sh/ruff/)
- **行宽限制**：100 字符
- **Python 版本**：≥ 3.10（使用 `X | Y` 类型联合语法）
- **类型注解**：全面使用类型注解

```bash
# 代码检查
ruff check src/

# 格式检查
ruff format --check src/

# 自动修复
ruff check --fix src/
ruff format src/
```

## 添加新数据源

### 1. 创建客户端文件

根据数据源类型，在对应目录创建文件：

- 论文：`src/souwen/paper/<source_name>.py`
- 专利：`src/souwen/patent/<source_name>.py`
- 搜索引擎：`src/souwen/web/<source_name>.py`

### 2. 选择基类

- **有正式 API**：继承 `SouWenHttpClient`
- **需要 HTML 爬取**：继承 `BaseScraper`
- **需要 OAuth**：继承 `OAuthClient`

### 3. 实现搜索方法

```python
from souwen.http_client import SouWenHttpClient
from souwen.models import SearchResponse, PaperResult, SourceType

class MySourceClient(SouWenHttpClient):
    def __init__(self, api_key: str | None = None):
        config = get_config()
        self.api_key = api_key or config.my_source_api_key
        super().__init__(base_url="https://api.example.com")

    async def search(self, query: str, per_page: int = 10) -> SearchResponse:
        resp = await self.get("/search", params={"q": query, "limit": per_page})
        data = resp.json()
        results = [self._parse_result(item) for item in data["results"]]
        return SearchResponse(
            query=query,
            source=SourceType.my_source,
            total_results=data.get("total"),
            results=results,
            per_page=per_page,
        )

    def _parse_result(self, item: dict) -> PaperResult:
        return PaperResult(
            source=SourceType.my_source,
            title=item["title"],
            # ... 映射所有字段
        )
```

### 4. 注册数据源

1. **models.py** — 在 `SourceType` 枚举中添加新值：

   ```python
   class SourceType(str, Enum):
       my_source = "my_source"
   ```

2. **models.py** — 在 `ALL_SOURCES` 中添加条目：

   ```python
   ALL_SOURCES = {
       "paper": [
           # ...
           ("my_source", True, "My Source 描述"),  # (名称, 需要Key, 描述)
       ],
   }
   ```

3. **config.py** — 如需配置字段，在 `SouWenConfig` 中添加：

   ```python
   my_source_api_key: str | None = None
   ```

4. **search.py** — 在对应搜索函数中添加路由：

   ```python
   # search_papers() 中的 source_map
   "my_source": lambda: _run_client(MySourceClient, "search", query=query, per_page=per_page),
   ```

5. **`__init__.py`** — 在模块的 `__init__.py` 中导出客户端类

### 5. 添加测试

在 `tests/` 目录创建测试文件，使用 `pytest-httpx` mock HTTP 请求：

```python
import pytest
from souwen.paper.my_source import MySourceClient

@pytest.fixture
def mock_response(httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/search",
        json={"results": [{"title": "Test Paper"}], "total": 1},
    )

@pytest.mark.asyncio
async def test_search(mock_response):
    async with MySourceClient(api_key="test") as client:
        resp = await client.search("test query")
        assert len(resp.results) == 1
        assert resp.results[0].title == "Test Paper"
```

## PR 流程

1. Fork 仓库并创建特性分支
2. 确保所有测试通过：`pytest tests/ -v`
3. 确保代码风格合规：`ruff check src/ && ruff format --check src/`
4. 提交 PR，描述清楚改动内容和动机
5. CI 会自动运行 lint + test
