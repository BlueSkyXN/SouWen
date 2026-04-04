"""论文搜索示例

演示如何使用 SouWen 搜索学术论文。
无需 API Key 的数据源（OpenAlex、arXiv、Crossref、DBLP）开箱即用。
"""

import asyncio

from souwen.paper.openalex import OpenAlexClient
from souwen.paper.semantic_scholar import SemanticScholarClient
from souwen.paper.arxiv import ArxivClient
from souwen.paper.crossref import CrossrefClient
from souwen.paper.dblp import DblpClient


async def demo_openalex():
    """OpenAlex 搜索示例（无需 Key）"""
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
    """Semantic Scholar 搜索示例（可选 Key）"""
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
    """arXiv 搜索示例（无需 Key）"""
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
    """Crossref 搜索示例（无需 Key）"""
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
    """DBLP 搜索示例（无需 Key）"""
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
    """运行所有论文搜索示例"""
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
