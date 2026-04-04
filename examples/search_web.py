"""网页搜索示例

演示三种用法：
1. 单引擎搜索（DuckDuckGo）
2. 并发多引擎聚合搜索
3. 指定引擎子集搜索
"""

import asyncio
from souwen.web import DuckDuckGoClient, web_search


async def main():
    # ===== 1. 单引擎搜索 =====
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

    # ===== 2. 并发多引擎聚合搜索 =====
    print("=" * 60)
    print("2. 多引擎并发聚合搜索（DuckDuckGo + Yahoo + Brave）")
    print("=" * 60)
    resp = await web_search("machine learning Python", max_results_per_engine=3)
    for r in resp.results:
        print(f"  [{r.engine}] {r.title}")
        print(f"    → {r.url}")
        print()

    # ===== 3. 指定引擎子集 =====
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
