"""网页搜索示例 — 展示三种网页搜索用法

文件用途：
    演示 SouWen 网页搜索功能的三种典型用法：
    1. 单引擎搜索（DuckDuckGo）— 简单直接
    2. 多引擎并发聚合搜索 — 获取更全面的搜索结果
    3. 指定引擎子集搜索 — 灵活组合不同数据源

核心函数清单：

    main() → None
        - 功能：按顺序演示三种网页搜索模式
        - 模式 1：单引擎搜索
            调用 DuckDuckGoClient 进行单一引擎搜索
            搜索示例：Python asyncio 教程
            输出：标题、URL、摘要
        - 模式 2：多引擎并发聚合搜索
            调用 web_search() 函数自动并发查询多个引擎
            搜索示例：机器学习 Python
            聚合引擎：DuckDuckGo、Yahoo、Brave
            输出：标题、URL、引擎来源
        - 模式 3：指定引擎子集搜索
            调用 web_search() 并指定 engines 参数筛选
            搜索示例：Rust vs Python 性能对比
            选定引擎：DuckDuckGo、Brave
            输出：结果总数、标题、URL

模块依赖：
    - souwen.web: 网页搜索引擎
    - asyncio: 异步编程支持

执行方式：
    python examples/search_web.py
"""

import asyncio
from souwen.web import DuckDuckGoClient, web_search


async def main():
    """展示三种网页搜索用法"""
    # ===== 模式 1：单引擎搜索 =====
    # 适用场景：需要快速搜索，对结果来源无特殊要求
    print("=" * 60)
    print("1. DuckDuckGo 单引擎搜索")
    print("=" * 60)
    async with DuckDuckGoClient() as client:
        results = await client.search("Python asyncio tutorial", max_results=5)
        for r in results.results:
            print(f"  {r.title}")
            print(f"    → {r.url}")
            if r.snippet:
                print(f"    {r.snippet[:80]}...")
            print()

    # ===== 模式 2：多引擎并发聚合搜索 =====
    # 适用场景：需要全面的搜索结果，希望获取多个引擎的结果
    # 优势：并发查询，性能高效；自动去重和聚合
    print("=" * 60)
    print("2. 多引擎并发聚合搜索（DuckDuckGo + Yahoo + Brave）")
    print("=" * 60)
    resp = await web_search("machine learning Python", max_results_per_engine=3)
    for r in resp.results:
        print(f"  [{r.engine}] {r.title}")
        print(f"    → {r.url}")
        print()

    # ===== 模式 3：指定引擎子集搜索 =====
    # 适用场景：希望使用特定的搜索引擎组合
    # 灵活性：可根据搜索类型选择最合适的引擎
    print("=" * 60)
    print("3. 指定引擎子集搜索（仅 DuckDuckGo + Brave）")
    print("=" * 60)
    resp = await web_search(
        "Rust vs Python performance",
        engines=["duckduckgo", "brave"],
        max_results_per_engine=3,
    )
    print(f"共 {resp.total_results} 条结果")
    for r in resp.results:
        print(f"  [{r.engine}] {r.title} → {r.url}")


if __name__ == "__main__":
    asyncio.run(main())
