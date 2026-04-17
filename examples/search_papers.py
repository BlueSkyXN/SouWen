"""论文搜索示例 — 展示如何使用 SouWen 搜索学术论文

文件用途：
    演示 SouWen 论文搜索功能，展示多个免费或开放 API 数据源的用法。
    包括 OpenAlex、Semantic Scholar、arXiv、Crossref、DBLP 等五大数据源。

核心函数清单：

    demo_openalex() → None
        - 功能：OpenAlex 搜索演示（无需 API Key，推荐填写邮箱）
        - 搜索示例：网络安全与深度学习相关论文
        - 输出：论文标题、发表年份、被引用数、DOI

    demo_semantic_scholar() → None
        - 功能：Semantic Scholar 搜索演示（可选 API Key）
        - 搜索示例：Transformer 架构相关论文
        - 输出：论文标题、TLDR（一句话总结）、被引用数

    demo_arxiv() → None
        - 功能：arXiv 预印本搜索演示（无需 Key）
        - 搜索示例：计算机科学/人工智能领域大语言模型论文
        - 输出：论文标题、PDF 下载链接

    demo_crossref() → None
        - 功能：Crossref 搜索演示（DOI 权威数据源，无需 Key）
        - 搜索示例：软件定义网络相关论文
        - 输出：论文标题、DOI、期刊名称

    demo_dblp() → None
        - 功能：DBLP 搜索演示（计算机科学权威索引，无需 Key）
        - 搜索示例：联邦学习相关论文
        - 输出：论文标题、发表场所、发表年份

    main() → None
        - 功能：按推荐顺序运行所有论文搜索示例
        - 执行流程：先运行无 Key 的数据源（OpenAlex、arXiv、Crossref、DBLP），
                  再运行可选 Key 的数据源（Semantic Scholar）
        - 输出提示：包括 API Key 配置建议

配置环境变量（可选提速）：
    - SOUWEN_OPENALEX_EMAIL: OpenAlex 注册邮箱，进入 polite pool 获得更高速率
    - SOUWEN_SEMANTIC_SCHOLAR_API_KEY: Semantic Scholar API Key，提升请求速率

执行方式：
    python examples/search_papers.py
"""

import asyncio

from souwen.paper.openalex import OpenAlexClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.dblp import DblpClient


async def demo_openalex():
    """OpenAlex 搜索示例（无需 Key）

    特点：
        - 免费、无需认证
        - 设置邮箱环境变量可进入 polite pool 获得更高速率
        - 包含完整的论文元数据（包括开放获取 URL）
    """
    print("=" * 60)
    print("📚 OpenAlex 搜索")
    print("=" * 60)

    async with OpenAlexClient() as client:
        results = await client.search("network security deep learning", per_page=5)
        print(f"共找到 {results.total_results} 条结果\n")
        for paper in results.results:
            print(f"  📄 {paper.title}")
            print(f"     年份: {paper.year} | 引用: {paper.citation_count}")
            print(f"     DOI: {paper.doi or '无'}")
            print()


async def demo_semantic_scholar():
    """Semantic Scholar 搜索示例（可选 Key）

    特点：
        - 无 Key 也可用（但有速率限制）
        - 提供 TLDR（一句话摘要）
        - 支持语义理解搜索
    """
    print("=" * 60)
    print("🔬 Semantic Scholar 搜索")
    print("=" * 60)

    async with SemanticScholarClient() as client:
        results = await client.search("transformer architecture", limit=5)
        for paper in results.results:
            print(f"  📄 {paper.title}")
            print(f"     TLDR: {paper.tldr or '无'}")
            print(f"     引用: {paper.citation_count}")
            print()


async def demo_arxiv():
    """arXiv 搜索示例（无需 Key）

    特点：
        - 预印本服务器，文献新速度快
        - 支持标准搜索语法（cat:分类, ti:标题等）
        - 提供 PDF 下载链接
    """
    print("=" * 60)
    print("📝 arXiv 搜索")
    print("=" * 60)

    async with ArxivClient() as client:
        results = await client.search("cat:cs.AI AND ti:large language model", max_results=5)
        for paper in results.results:
            print(f"  📄 {paper.title}")
            print(f"     PDF: {paper.pdf_url}")
            print()


async def demo_crossref():
    """Crossref 搜索示例（无需 Key）

    特点：
        - DOI 权威数据源
        - 涵盖期刊、会议、图书等多种出版物
        - 元数据完整、更新及时
    """
    print("=" * 60)
    print("🔗 Crossref 搜索 (DOI 权威源)")
    print("=" * 60)

    async with CrossrefClient() as client:
        results = await client.search("software defined networking", rows=5)
        for paper in results.results:
            print(f"  📄 {paper.title}")
            print(f"     DOI: {paper.doi}")
            print(f"     期刊: {paper.journal or '无'}")
            print()


async def demo_dblp():
    """DBLP 搜索示例（无需 Key）

    特点：
        - 计算机科学研究权威索引
        - 收录学术论文、会议论文
        - 拥有完整的发表记录和引用关系
    """
    print("=" * 60)
    print("💻 DBLP 搜索 (计算机科学权威索引)")
    print("=" * 60)

    async with DblpClient() as client:
        results = await client.search("federated learning", hits=5)
        for paper in results.results:
            print(f"  📄 {paper.title}")
            print(f"     发表于: {paper.venue or '未知'}")
            print(f"     年份: {paper.year}")
            print()


async def main():
    """运行所有论文搜索示例

    执行顺序：
        1. 无需 Key 的数据源（推荐优先使用）：OpenAlex、arXiv、Crossref、DBLP
        2. 可选 Key 的数据源（可提升速率）：Semantic Scholar

    输出建议：
        - SOUWEN_OPENALEX_EMAIL：注册邮箱以进入 polite pool
        - SOUWEN_SEMANTIC_SCHOLAR_API_KEY：官方 API 密钥
    """
    print("\n🔍 SouWen 论文搜索示例\n")

    # 无需 Key 的数据源
    await demo_openalex()
    await demo_arxiv()
    await demo_crossref()
    await demo_dblp()

    # 可选 Key（无 Key 也可用，但限速）
    await demo_semantic_scholar()

    print("\n✅ 示例完成！")
    print("提示: 设置 SOUWEN_OPENALEX_EMAIL 可进入 OpenAlex polite pool（更快响应）")
    print("提示: 设置 SOUWEN_SEMANTIC_SCHOLAR_API_KEY 可提升 Semantic Scholar 速率")


if __name__ == "__main__":
    asyncio.run(main())
