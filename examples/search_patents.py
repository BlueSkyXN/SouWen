"""专利搜索示例 — 展示如何使用 SouWen 搜索专利信息

文件用途：
    演示 SouWen 专利搜索功能，展示多个开放或付费 API 数据源的用法。
    包括 PatentsView（美国专利）、PQAI（语义搜索）、EPO OPS（欧洲专利）三个数据源。

核心函数清单：

    demo_patentsview() → None
        - 功能：PatentsView 搜索演示（美国专利，无需 Key）
        - 搜索方式：按申请人（Assignee）搜索 Huawei 相关专利
        - 输出：专利号、专利标题、申请人、公开日期
        - 限制条件：仅适用于美国 USPTO 数据

    demo_pqai() → None
        - 功能：PQAI 语义搜索演示（无需 Key）
        - 搜索方式：自然语言语义搜索（不需要精确的专利检索语法）
        - 搜索示例：无线网络接入认证与机器学习相关专利
        - 优势：支持概念性搜索，无需掌握检索语法
        - 输出：专利号、专利标题

    demo_epo() → None
        - 功能：EPO OPS 搜索演示（欧洲专利办公室，需 API Key）
        - 搜索方式：高级 CQL 检索语法（标题 ti、申请人 pa 等）
        - 搜索示例：标题包含"人工智能"且申请人为"Huawei"的专利
        - 前提条件：需配置 SOUWEN_EPO_CONSUMER_KEY 和 SOUWEN_EPO_CONSUMER_SECRET
        - 注册地址：https://developers.epo.org/
        - 错误处理：Key 未配置时友好提示

    main() → None
        - 功能：按推荐顺序运行所有专利搜索示例
        - 执行流程：先运行无 Key 的数据源（PatentsView、PQAI），
                  再运行需 Key 的数据源（EPO OPS）
        - 输出建议：包括数据源配置参考

配置环境变量（可选）：
    - 无 Key 数据源无需配置，开箱即用
    - SOUWEN_EPO_CONSUMER_KEY 和 SOUWEN_EPO_CONSUMER_SECRET：EPO API 凭证

执行方式：
    python examples/search_patents.py
"""

import asyncio

from souwen.patent.patentsview import PatentsViewClient
from souwen.patent.pqai import PqaiClient


async def demo_patentsview():
    """PatentsView 搜索示例（无需 Key，美国专利）

    特点：
        - 美国 USPTO 官方数据源
        - 提供多种检索方式：按申请人、CPC 分类、年份等
        - 返回完整的专利元数据
    """
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
    """PQAI 语义搜索示例（无需 Key）

    特点：
        - 支持自然语言语义搜索
        - 无需学习复杂的检索语法
        - 理解概念相关性而非字面匹配
    """
    print("=" * 60)
    print("🧠 PQAI 语义搜索")
    print("=" * 60)

    async with PqaiClient() as client:
        # 自然语言搜索
        results = await client.search(
            "wireless network access point authentication using machine learning",
            n_results=5,
        )
        print("语义搜索结果:\n")
        for patent in results.results:
            print(f"  📋 {patent.patent_id}: {patent.title}")
            print()


async def demo_epo():
    """EPO OPS 搜索示例（需 Key）

    特点：
        - 欧洲专利办公室官方 API
        - 支持高级 CQL（共同查询语言）检索
        - 覆盖欧洲及国际专利数据

    错误处理：
        - 捕获 ImportError/RuntimeError，友好提示 Key 配置
    """
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
    """运行所有专利搜索示例

    执行顺序：
        1. 无需 Key 的数据源（推荐优先使用）：PatentsView、PQAI
        2. 需要 Key 的数据源（功能更强大）：EPO OPS

    数据源对比：
        - PatentsView：美国专利，结构化数据，支持多维度检索
        - PQAI：全球专利，语义搜索，适合概念性查询
        - EPO OPS：欧洲专利，高级语法支持，数据权威性强
    """
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
