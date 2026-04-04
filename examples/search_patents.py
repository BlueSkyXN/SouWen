"""专利搜索示例

演示如何使用 SouWen 搜索专利信息。
无需 API Key 的数据源（PatentsView、PQAI）开箱即用。
"""

import asyncio

from souwen.patent.patentsview import PatentsViewClient
from souwen.patent.pqai import PqaiClient


async def demo_patentsview():
    """PatentsView 搜索示例（无需 Key，美国专利）"""
    print("=" * 60)
    print("🇺🇸 PatentsView 搜索 (USPTO)")
    print("=" * 60)

    async with PatentsViewClient() as client:
        # 按公司搜索
        results = await client.search_by_assignee("Huawei", per_page=5)
        print(f"Huawei 相关专利，共 {results.total_results} 条\n")
        for patent in results.results:
            print(f"  📋 {patent.patent_id}: {patent.title}")
            print(f"     申请人: {', '.join(a.name for a in patent.applicants)}")
            print(f"     日期: {patent.publication_date}")
            print()


async def demo_pqai():
    """PQAI 语义搜索示例（无需 Key）"""
    print("=" * 60)
    print("🧠 PQAI 语义搜索")
    print("=" * 60)

    async with PqaiClient() as client:
        # 自然语言搜索
        results = await client.search(
            "wireless network access point authentication using machine learning",
            n_results=5,
        )
        print(f"语义搜索结果:\n")
        for patent in results.results:
            print(f"  📋 {patent.patent_id}: {patent.title}")
            print()


async def demo_epo():
    """EPO OPS 搜索示例（需 Key）"""
    print("=" * 60)
    print("🇪🇺 EPO OPS 搜索 (需配置 Key)")
    print("=" * 60)

    try:
        from souwen.patent.epo_ops import EpoOpsClient

        async with EpoOpsClient() as client:
            results = await client.search('ti="artificial intelligence" AND pa="Huawei"')
            for patent in results.results:
                print(f"  📋 {patent.patent_id}: {patent.title}")
                print()
    except Exception as e:
        print(f"  ⚠️  EPO OPS 不可用: {e}")
        print("  提示: 设置 SOUWEN_EPO_CONSUMER_KEY 和 SOUWEN_EPO_CONSUMER_SECRET")
        print("  注册: https://developers.epo.org/")
        print()


async def main():
    """运行所有专利搜索示例"""
    print("\n🔍 SouWen 专利搜索示例\n")

    # 无需 Key 的数据源
    await demo_patentsview()
    await demo_pqai()

    # 需要 Key 的数据源
    await demo_epo()

    print("\n✅ 示例完成！")
    print("提示: PatentsView 和 PQAI 无需任何配置即可使用")
    print("提示: 更多数据源配置请参考 .env.example")


if __name__ == "__main__":
    asyncio.run(main())
