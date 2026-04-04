"""PubMed / NCBI E-utilities 客户端

官方文档: https://www.ncbi.nlm.nih.gov/books/NBK25501/
鉴权: 可选 API Key，无 Key 限流 3 req/s，有 Key 10 req/s
搜索模式: 两步式 esearch → efetch
返回: XML
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from souwen.config import get_config
from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# 无 Key: 3 req/s, 有 Key: 10 req/s
_NO_KEY_RPS = 3.0
_KEYED_RPS = 10.0


class PubMedClient:
    """PubMed / NCBI E-utilities 生物医学文献搜索客户端。

    采用两步搜索模式:
    1. esearch.fcgi — 获取 PMID 列表
    2. efetch.fcgi — 根据 PMID 批量获取详情
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 PubMed 客户端。

        Args:
            api_key: NCBI API Key。未提供时从全局配置读取。
        """
        cfg = get_config()
        self.api_key: str | None = api_key or getattr(cfg, "pubmed_api_key", None)

        self._client = SouWenHttpClient(base_url=_BASE_URL)
        rps = _KEYED_RPS if self.api_key else _NO_KEY_RPS
        self._limiter = TokenBucketLimiter(rate=rps, capacity=rps)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> PubMedClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _common_params(self) -> dict[str, str]:
        """构建公共请求参数。"""
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @classmethod
    def _parse_article(cls, article_el: ET.Element) -> PaperResult:
        """将 PubmedArticle XML 元素转换为 PaperResult。

        Args:
            article_el: ``<PubmedArticle>`` XML 元素。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            medline = article_el.find("MedlineCitation")
            if medline is None:
                raise ParseError("缺少 MedlineCitation 元素")

            pmid_el = medline.find("PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            article = medline.find("Article")
            if article is None:
                raise ParseError("缺少 Article 元素")

            # 标题
            title_el = article.find("ArticleTitle")
            title = title_el.text if title_el is not None else ""
            # 可能包含子标签，拼接所有文本
            if title_el is not None:
                title = "".join(title_el.itertext())

            # 摘要
            abstract_parts: list[str] = []
            abstract_el = article.find("Abstract")
            if abstract_el is not None:
                for text_el in abstract_el.findall("AbstractText"):
                    label = text_el.get("Label", "")
                    text = "".join(text_el.itertext()).strip()
                    if label and text:
                        abstract_parts.append(f"{label}: {text}")
                    elif text:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            # 作者列表
            authors: list[Author] = []
            author_list_el = article.find("AuthorList")
            if author_list_el is not None:
                for author_el in author_list_el.findall("Author"):
                    last = author_el.findtext("LastName", "")
                    fore = author_el.findtext("ForeName", "")
                    name = f"{fore} {last}".strip()
                    # 机构
                    affiliations: list[str] = []
                    for aff_el in author_el.findall("AffiliationInfo/Affiliation"):
                        if aff_el.text:
                            affiliations.append(aff_el.text)
                    if name:
                        authors.append(
                            Author(name=name, affiliations=affiliations)
                        )

            # 发表日期
            year: int | None = None
            pub_date: str | None = None
            journal_el = article.find("Journal")
            if journal_el is not None:
                date_el = journal_el.find("JournalIssue/PubDate")
                if date_el is not None:
                    y = date_el.findtext("Year")
                    m = date_el.findtext("Month", "01")
                    d = date_el.findtext("Day", "01")
                    if y:
                        year = int(y)
                        # 月份可能是英文缩写
                        month_map = {
                            "Jan": "01", "Feb": "02", "Mar": "03",
                            "Apr": "04", "May": "05", "Jun": "06",
                            "Jul": "07", "Aug": "08", "Sep": "09",
                            "Oct": "10", "Nov": "11", "Dec": "12",
                        }
                        m_num = month_map.get(m, m.zfill(2) if m.isdigit() else "01")
                        d_num = d.zfill(2) if d.isdigit() else "01"
                        pub_date = f"{y}-{m_num}-{d_num}"

            # DOI
            doi: str | None = None
            pub_data = article_el.find("PubmedData")
            if pub_data is not None:
                for aid in pub_data.findall("ArticleIdList/ArticleId"):
                    if aid.get("IdType") == "doi":
                        doi = aid.text
                        break

            # 期刊名
            journal_title = ""
            if journal_el is not None:
                jt_el = journal_el.find("Title")
                if jt_el is not None:
                    journal_title = jt_el.text or ""

            # MeSH 关键词
            mesh_terms: list[str] = []
            mesh_list = medline.find("MeshHeadingList")
            if mesh_list is not None:
                for mesh in mesh_list.findall("MeshHeading/DescriptorName"):
                    if mesh.text:
                        mesh_terms.append(mesh.text)

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.PUBMED,
                source_id=pmid,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                pdf_url=None,  # PubMed 不直接提供 PDF
                citation_count=None,
                extra={
                    "journal": journal_title,
                    "mesh_terms": mesh_terms[:10],
                    "pmid": pmid,
                },
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"解析 PubMed article 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        retmax: int = 10,
        retstart: int = 0,
    ) -> SearchResponse:
        """搜索 PubMed 文献（两步: esearch → efetch）。

        Args:
            query: PubMed 检索式，支持 MeSH 等高级语法。
            retmax: 返回条数，上限 10000。
            retstart: 起始偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        # ---- Step 1: esearch 获取 PMID 列表 ----
        await self._limiter.acquire()

        search_params = self._common_params()
        search_params.update(
            {
                "db": "pubmed",
                "term": query,
                "retmax": str(min(retmax, 10000)),
                "retstart": str(retstart),
                "retmode": "xml",
            }
        )

        search_resp = await self._client.get("/esearch.fcgi", params=search_params)
        search_root = ET.fromstring(search_resp.text)

        # 总数
        count_el = search_root.find("Count")
        total = int(count_el.text) if count_el is not None and count_el.text else 0

        # PMID 列表
        pmids: list[str] = []
        id_list = search_root.find("IdList")
        if id_list is not None:
            for id_el in id_list.findall("Id"):
                if id_el.text:
                    pmids.append(id_el.text)

        if not pmids:
            return SearchResponse(
                query=query,
                total=total,
                page=(retstart // retmax) + 1 if retmax else 1,
                per_page=retmax,
                results=[],
                source=SourceType.PUBMED,
            )

        # ---- Step 2: efetch 获取详情 ----
        results = await self.fetch(pmids)

        return SearchResponse(
            query=query,
            total=total,
            page=(retstart // retmax) + 1 if retmax else 1,
            per_page=retmax,
            results=results,
            source=SourceType.PUBMED,
        )

    async def fetch(self, pmids: list[str]) -> list[PaperResult]:
        """根据 PMID 列表批量获取论文详情。

        Args:
            pmids: PubMed ID 列表。

        Returns:
            PaperResult 列表。

        Raises:
            NotFoundError: 无有效结果。
        """
        if not pmids:
            return []

        await self._limiter.acquire()

        fetch_params = self._common_params()
        fetch_params.update(
            {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "rettype": "abstract",
            }
        )

        fetch_resp = await self._client.get("/efetch.fcgi", params=fetch_params)
        root = ET.fromstring(fetch_resp.text)

        results: list[PaperResult] = []
        for article_el in root.findall("PubmedArticle"):
            try:
                results.append(self._parse_article(article_el))
            except ParseError as exc:
                logger.warning("跳过解析失败的 PubMed 文章: %s", exc)
                continue

        return results
