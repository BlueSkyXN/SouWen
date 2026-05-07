"""OpenAIRE Research Products API 客户端

官方端点: https://api.openaire.eu/search/researchProducts
鉴权: 可选 Bearer Token（注册：https://aai.openaire.eu/）
限流: 保守 3 req/s（匿名访问限制更紧）
返回: JSON（format=json，结构嵌套且使用 ``$`` 与 ``@classid`` 等键名）

文件用途：OpenAIRE 欧盟开放科研聚合平台搜索客户端，覆盖论文、
            预印本、数据集等多类研究成果，整合自欧盟各国机构仓储。

参考来源：OpenAIRE Search API 官方文档
         https://graph.openaire.eu/docs/apis/search-api/research-products

函数/类清单：
    OpenAireClient（类）
        - 功能：OpenAIRE 检索客户端，解析嵌套 JSON 响应为统一数据模型
        - 关键属性：api_key (str|None) 可选 API Key,
                   _client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（3 req/s）

    _extract_text(obj) -> str
        - 功能：从 OpenAIRE ``{"$": "text"}`` 嵌套结构中安全提取文本
        - 输入：dict / str / 任意类型
        - 输出：解析出的字符串（缺失返回空串）

    _as_list(value) -> list
        - 功能：OpenAIRE 字段在单值与多值时类型不一致，统一转 list
        - 输入：任意值
        - 输出：list（None → []，单值 → [value]）

    _parse_result(result: dict) -> PaperResult
        - 功能：将 OpenAIRE 单条 result 转换为 PaperResult
        - 输入：OpenAIRE response.results.result 的单个元素
        - 输出：统一的 PaperResult 模型

    search(query: str, size: int = 10) -> SearchResponse
        - 功能：按关键词搜索 OpenAIRE 研究成果
        - 输入：query 关键词, size 每页条数
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - PaperResult: 统一论文数据模型
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openaire.eu"

# 保守限流：匿名访问 OpenAIRE 限制较严，按 3 req/s 控制
_DEFAULT_RPS = 3.0


def _as_list(value: Any) -> list[Any]:
    """统一字段为列表。OpenAIRE 在单值与多值时返回类型不一致。

    Args:
        value: 任意值。

    Returns:
        list；None 转为 []，标量转为 [value]。
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class OpenAireClient:
    """OpenAIRE 欧盟开放科研基础设施搜索客户端。

    特点:
        - 聚合欧盟各国机构仓储，覆盖论文/预印本/数据集等
        - 可选 API Key（匿名亦可访问，但限流更严）
        - JSON 响应使用 ``{"$": "text", "@classid": "..."}`` 嵌套结构，
          需通过 :func:`_extract_text` 与 :func:`_as_list` 安全解析
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 OpenAIRE 客户端。

        Args:
            api_key: OpenAIRE API Key（可选）。未提供时从全局配置读取，
                     仍为空则匿名访问。
        """
        cfg = get_config()
        self.api_key: str | None = (
            api_key or cfg.resolve_api_key("openaire", "openaire_api_key") or None
        )

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self._client = SouWenHttpClient(base_url=_BASE_URL, headers=headers, source_name="openaire")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> OpenAireClient:
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

    @staticmethod
    def _extract_text(obj: Any) -> str:
        """从 OpenAIRE ``{"$": "text"}`` 嵌套结构中提取文本。

        Args:
            obj: dict（含 ``$`` 键）/ str / 其他类型。

        Returns:
            提取出的字符串；缺失或类型不匹配时返回空串。
        """
        if isinstance(obj, dict):
            value = obj.get("$", "")
            return str(value) if value is not None else ""
        if isinstance(obj, str):
            return obj
        if obj is None:
            return ""
        return str(obj)

    @classmethod
    def _parse_result(cls, result: dict[str, Any]) -> PaperResult:
        """将 OpenAIRE 单条 result 转换为 PaperResult。

        OpenAIRE JSON 响应大致结构::

            result -> metadata -> oaf:entity -> oaf:result -> {
                title, creator, description, pid, dateofacceptance,
                journal, children.instance[].webresource[].url, ...
            }

        Args:
            result: OpenAIRE response.results.result 的单个元素。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            metadata = result.get("metadata") or {}
            entity = metadata.get("oaf:entity") or {}
            oaf_result = entity.get("oaf:result") or {}

            # 标题：可能是 dict 或 list[dict]，优先取 classid="main title"
            title = ""
            for t in _as_list(oaf_result.get("title")):
                text = cls._extract_text(t)
                if isinstance(t, dict) and t.get("@classid") == "main title" and text:
                    title = text
                    break
                if not title and text:
                    title = text

            # 作者：creator 可能为 dict 或 list[dict]
            authors: list[Author] = []
            for c in _as_list(oaf_result.get("creator")):
                name = cls._extract_text(c).strip()
                if name:
                    authors.append(Author(name=name))

            # 摘要：description 可能为 dict 或 list[dict]
            abstract = ""
            for d in _as_list(oaf_result.get("description")):
                text = cls._extract_text(d).strip()
                if text:
                    abstract = text
                    break

            # DOI：pid 列表中 classid=doi 的项
            doi: str | None = None
            for pid in _as_list(oaf_result.get("pid")):
                if isinstance(pid, dict) and pid.get("@classid", "").lower() == "doi":
                    doi_val = cls._extract_text(pid).strip()
                    if doi_val:
                        doi = doi_val
                        break

            # 日期：dateofacceptance（YYYY-MM-DD 或 YYYY）
            pub_date_str = cls._extract_text(oaf_result.get("dateofacceptance")).strip()
            pub_date: str | None = pub_date_str or None
            year: int | None = None
            if pub_date_str and len(pub_date_str) >= 4:
                try:
                    year = int(pub_date_str[:4])
                except ValueError:
                    year = None

            # 期刊
            journal_obj = oaf_result.get("journal")
            journal: str | None = cls._extract_text(journal_obj).strip() or None

            # PDF / 全文 URL：children.instance[].webresource[].url
            pdf_url: str | None = None
            children = oaf_result.get("children") or {}
            instances = _as_list(children.get("instance"))
            for inst in instances:
                if not isinstance(inst, dict):
                    continue
                for wr in _as_list(inst.get("webresource")):
                    if not isinstance(wr, dict):
                        continue
                    url_val = cls._extract_text(wr.get("url")).strip()
                    if url_val:
                        pdf_url = url_val
                        break
                if pdf_url:
                    break

            # 资源类型
            resulttype = oaf_result.get("resulttype") or {}
            result_type_name = (
                resulttype.get("@classname") if isinstance(resulttype, dict) else None
            )

            # 语言
            language_obj = oaf_result.get("language") or {}
            language_name = (
                language_obj.get("@classname") if isinstance(language_obj, dict) else None
            )

            # source_url：优先 PDF URL，否则基于 DOI 构造，否则使用 OpenAIRE 站点
            if pdf_url:
                source_url = pdf_url
            elif doi:
                source_url = f"https://doi.org/{doi}"
            else:
                # OpenAIRE 内部 ID（在 result.header.dri:objIdentifier）
                header = result.get("header") or {}
                obj_id = cls._extract_text(header.get("dri:objIdentifier")).strip()
                source_url = (
                    f"https://explore.openaire.eu/search/publication?pid={obj_id}"
                    if obj_id
                    else "https://explore.openaire.eu/"
                )

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract or None,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="openaire",
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # OpenAIRE 搜索接口不直接给出引用数
                journal=journal,
                raw={
                    "result_type": result_type_name,
                    "language": language_name,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 OpenAIRE result 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        size: int = 10,
    ) -> SearchResponse:
        """搜索 OpenAIRE 研究成果。

        Args:
            query: 检索关键词。
            size: 每页条数。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "keywords": query,
            "page": 1,
            "size": size,
            "format": "json",
        }

        resp = await self._client.get("/search/researchProducts", params=params)
        data: dict[str, Any] = resp.json()

        response_block = data.get("response") or {}

        # 总数：header.total.$
        total: int | None = None
        header = response_block.get("header") or {}
        total_obj = header.get("total")
        if isinstance(total_obj, dict):
            try:
                total = int(total_obj.get("$", 0))
            except (TypeError, ValueError):
                total = None
        elif isinstance(total_obj, (int, str)):
            try:
                total = int(total_obj)
            except (TypeError, ValueError):
                total = None

        # 结果：results.result 可能是 dict（单条）或 list
        results_block = response_block.get("results") or {}
        raw_results = _as_list(results_block.get("result"))

        results: list[PaperResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的 OpenAIRE result: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total if total is not None else len(results),
            page=1,
            per_page=size,
            results=results,
            source="openaire",
        )
