"""Metaso 搜索示例

演示如何使用 MetasoClient 进行文档、网页和学术搜索，以及使用 Reader API 提取网页内容。
"""

import asyncio
import os

from souwen.web import MetasoClient


async def main():
    # 从环境变量获取 API Key
    api_key = os.getenv("SOUWEN_METASO_API_KEY") or "mk-YOUR_API_KEY"

    print("=== Metaso 搜索示例 ===\n")

    # 1. 文档搜索
    print("1. 文档搜索（scope=document）")
    async with MetasoClient(api_key=api_key) as client:
        try:
            results = await client.search("AI", scope="document", max_results=3)
            print(f"   找到 {len(results.results)} 条文档结果:")
            for i, r in enumerate(results.results, 1):
                print(f"   {i}. {r.title}")
                print(f"      URL: {r.url}")
                print(f"      摘要: {r.snippet[:100]}...")
                print()
        except Exception as e:
            print(f"   错误: {e}\n")

    # 2. 网页搜索
    print("\n2. 网页搜索（scope=webpage）")
    async with MetasoClient(api_key=api_key) as client:
        try:
            results = await client.search("Python asyncio", scope="webpage", max_results=3)
            print(f"   找到 {len(results.results)} 条网页结果:")
            for i, r in enumerate(results.results, 1):
                print(f"   {i}. {r.title}")
                print(f"      URL: {r.url}")
                print(f"      摘要: {r.snippet[:100]}...")
                print()
        except Exception as e:
            print(f"   错误: {e}\n")

    # 3. 学术搜索
    print("\n3. 学术搜索（scope=scholar）")
    async with MetasoClient(api_key=api_key) as client:
        try:
            results = await client.search("machine learning", scope="scholar", max_results=3)
            print(f"   找到 {len(results.results)} 条学术结果:")
            for i, r in enumerate(results.results, 1):
                print(f"   {i}. {r.title}")
                print(f"      URL: {r.url}")
                print(f"      摘要: {r.snippet[:100]}...")
                print()
        except Exception as e:
            print(f"   错误: {e}\n")

    # 4. Reader API - 提取网页内容
    print("\n4. Reader API - 提取网页内容")
    async with MetasoClient(api_key=api_key) as client:
        try:
            test_url = "https://www.163.com/news/article/K56809DQ000189FH.html"
            resp = await client.reader(test_url)
            if resp.results and not resp.results[0].error:
                result = resp.results[0]
                print(f"   成功提取 URL: {test_url}")
                print(f"   内容长度: {len(result.content)} 字符")
                print(f"   前 200 字符: {result.content[:200]}...")
            else:
                print(f"   提取失败: {resp.results[0].error if resp.results else '未知错误'}")
        except Exception as e:
            print(f"   错误: {e}\n")


if __name__ == "__main__":
    print("注意: 请设置环境变量 SOUWEN_METASO_API_KEY 或修改代码中的 API Key")
    print("示例: export SOUWEN_METASO_API_KEY=mk-YOUR_API_KEY\n")
    asyncio.run(main())
