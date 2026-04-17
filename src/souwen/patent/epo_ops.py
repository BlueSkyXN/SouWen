"""EPO OPS (Open Patent Services) 客户端

欧洲专利局数据服务，OAuth 2.0 鉴权。
注册地址: https://developers.epo.org/
官方文档: https://developers.epo.org/ops-v3-2/apis

文件用途：
    EPO OPS 客户端实现，提供专利搜索、详情、族信息、法律状态等多维查询。
    支持 CQL (Common Query Language) 查询语法，返回 XML 格式数据。

函数/类清单：
    EpoOpsClient（类）
        - 功能：EPO OPS 专利数据客户端，管理 OAuth 连接和 XML 解析
        - 关键属性：BASE_URL (str) API 基础地址，TOKEN_URL (str) OAuth 端点
        - 关键变量：_http (OAuthClient) OAuth HTTP 客户端，_limiter 速率限制器
    
    search(cql_query: str, range_begin: int = 1, range_end: int = 10) -> SearchResponse
        - 功能：使用 CQL 查询搜索欧洲专利
        - 输入：cql_query CQL 查询表达式，range_begin/end 结果范围
        - 输出：SearchResponse 包含总数和专利列表
    
    get_publication(doc_id: str, doc_type: str = "publication", format: str = "epodoc") -> PatentResult
        - 功能：获取出版物（专利或申请）详情
        - 输入：doc_id 文档标识符，doc_type 类型，format 标识符格式
        - 输出：PatentResult 专利详情
        - 异常：NotFoundError 文档不存在时抛出
    
    get_family(doc_id: str) -> list[PatentResult]
        - 功能：获取专利族信息（同族专利列表）
        - 输入：doc_id 文档标识符
        - 输出：专利族成员列表
    
    get_legal_status(doc_id: str) -> list[dict[str, Any]]
        - 功能：获取 INPADOC 法律状态（审查进度、维持费等重要事件）
        - 输入：doc_id 文档标识符
        - 输出：法律事件列表
    
    get_claims(doc_id: str) -> str | None
        - 功能：获取权利要求书文本
        - 输入：doc_id 文档标识符
        - 输出：权利要求文本或 None
    
    get_description(doc_id: str) -> str | None
        - 功能：获取说明书文本（发明背景、技术方案等）
        - 输入：doc_id 文档标识符
        - 输出：说明书文本或 None
    
    _parse_xml(text: str) -> ET.Element（静态方法）
        - 功能：安全解析 XML 响应
        - 异常：ParseError XML 格式错误时抛出
    
    _extract_search_results(root: ET.Element) -> list[PatentResult]
        - 功能：从搜索 XML 中提取专利列表
    
    _exchange_doc_to_result(doc: ET.Element) -> PatentResult（静态方法）
        - 功能：将 EPO exchange-document XML 节点转换为 PatentResult

模块依赖：
    - defusedxml: 安全的 XML 解析（防止 XXE 攻击）
    - souwen.http_client: OAuth 连接管理
    - souwen.models: 统一数据模型
    - souwen.rate_limiter: 限流控制
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
import defusedxml.ElementTree as ET

from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError
from souwen.http_client import OAuthClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

# EPO OPS XML 命名空间（用于 XPath 和 find 操作）
_NS = {
    "ops": "http://ops.epo.org",
    "epo": "http://www.epo.org/exchange",
    "ft": "http://www.epo.org/fulltext",
}


class EpoOpsClient:
    """EPO OPS (Open Patent Services) 客户端

    访问欧洲专利局数据，支持 CQL 查询语法。
    需要 OAuth 2.0 客户端凭证 (consumer_key / consumer_secret)。

    Attributes:
        BASE_URL: EPO OPS API 基础地址
        TOKEN_URL: OAuth 2.0 令牌端点
    """

    BASE_URL = "https://ops.epo.org/3.2"
    TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"

    def __init__(self) -> None:
        """初始化 EPO OPS 客户端
        
        从配置读取 OAuth 凭证（consumer_key / consumer_secret），建立连接。
        
        Raises:
            ConfigError: 缺少必要的 OAuth 凭证时抛出
        """
        cfg = get_config()
        if not cfg.epo_consumer_key or not cfg.epo_consumer_secret:
            raise ConfigError(
                key="epo_consumer_key / epo_consumer_secret",
                service="EPO OPS",
                register_url="https://developers.epo.org/",
            )
        self._http = OAuthClient(
            base_url=self.BASE_URL,
            token_url=self.TOKEN_URL,
            client_id=cfg.epo_consumer_key,
            client_secret=cfg.epo_consumer_secret,
            source_name="epo_ops",
        )
        # EPO 免费配额 4GB/月，限流取决于用量级别
        self._limiter = TokenBucketLimiter(rate=2.0, burst=10)

    async def __aenter__(self) -> EpoOpsClient:
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def close(self) -> None:
        """关闭 HTTP 连接"""
        await self._http.close()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        cql_query: str,
        range_begin: int = 1,
        range_end: int = 10,
    ) -> SearchResponse:
        """使用 CQL 查询搜索专利

        Args:
            cql_query: CQL 查询表达式，例如 ``"ta=electric vehicle and pd>=2020"``
            range_begin: 结果起始位置（从 1 开始）
            range_end: 结果结束位置

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()
        # Range 参数指定返回结果的范围（1-based，包含两端）
        resp = await self._http.get(
            "/rest-services/published-data/search",
            params={"q": cql_query, "Range": f"{range_begin}-{range_end}"},
            headers={"Accept": "application/xml"},
        )

        root = self._parse_xml(resp.text)
        total = self._extract_total(root)
        patents = self._extract_search_results(root)

        per_page = max(range_end - range_begin + 1, 1)
        return SearchResponse(
            query=cql_query,
            source=SourceType.EPO_OPS,
            total_results=total,
            results=patents,
            page=(range_begin - 1) // per_page + 1,
            per_page=per_page,
        )

    async def get_publication(
        self,
        doc_id: str,
        doc_type: str = "publication",
        format: str = "epodoc",
    ) -> PatentResult:
        """获取出版物详情

        Args:
            doc_id: 文档标识符，例如 ``"EP1000000"``
            doc_type: 文档类型 (``publication`` / ``application``)
            format: 标识符格式 (``epodoc`` / ``docdb`` / ``original``)

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该出版物
        """
        await self._limiter.acquire()
        url = f"/rest-services/published-data/{doc_type}/{format}/{doc_id}"
        resp = await self._http.get(
            url,
            headers={"Accept": "application/xml"},
        )
        if resp.status_code == 404:
            raise NotFoundError(f"出版物 {doc_id} 未找到")

        root = self._parse_xml(resp.text)
        return self._extract_publication(root, doc_id)

    async def get_family(self, doc_id: str) -> list[PatentResult]:
        """获取专利族信息

        Args:
            doc_id: 文档标识符

        Returns:
            专利族成员列表
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/rest-services/family/publication/epodoc/{doc_id}",
            headers={"Accept": "application/xml"},
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利族 {doc_id} 未找到")

        root = self._parse_xml(resp.text)
        return self._extract_family_members(root)

    async def get_legal_status(self, doc_id: str) -> list[dict[str, Any]]:
        """获取 INPADOC 法律状态

        Args:
            doc_id: 文档标识符

        Returns:
            法律事件列表
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/rest-services/legal/publication/epodoc/{doc_id}",
            headers={"Accept": "application/xml"},
        )
        if resp.status_code == 404:
            raise NotFoundError(f"法律状态 {doc_id} 未找到")

        root = self._parse_xml(resp.text)
        events: list[dict[str, Any]] = []
        # 遍历所有 legal 元素，提取事件信息
        for ev in root.iter("{http://ops.epo.org}legal"):
            event: dict[str, Any] = {}
            # 提取每个子元素，去除命名空间前缀
            for child in ev:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                event[tag] = child.text
            if event:
                events.append(event)
        return events

    async def get_claims(self, doc_id: str) -> str | None:
        """获取权利要求书

        Args:
            doc_id: 文档标识符

        Returns:
            权利要求文本，若无则返回 None
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/rest-services/published-data/publication/epodoc/{doc_id}/claims",
            headers={"Accept": "application/xml"},
        )
        if resp.status_code == 404:
            return None

        root = self._parse_xml(resp.text)
        claims_parts: list[str] = []
        # 提取所有权利要求条文
        for claim in root.iter("{http://www.epo.org/fulltext}claim-text"):
            if claim.text:
                claims_parts.append(claim.text.strip())
        return "\n\n".join(claims_parts) if claims_parts else None

    async def get_description(self, doc_id: str) -> str | None:
        """获取说明书

        Args:
            doc_id: 文档标识符

        Returns:
            说明书文本，若无则返回 None
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/rest-services/published-data/publication/epodoc/{doc_id}/description",
            headers={"Accept": "application/xml"},
        )
        if resp.status_code == 404:
            return None

        root = self._parse_xml(resp.text)
        desc_parts: list[str] = []
        # 提取所有说明书段落
        for para in root.iter("{http://www.epo.org/fulltext}p"):
            if para.text:
                desc_parts.append(para.text.strip())
        return "\n\n".join(desc_parts) if desc_parts else None

    # ------------------------------------------------------------------
    # XML 解析辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_xml(text: str) -> ET.Element:
        """解析 XML 响应"""
        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise ParseError(f"EPO OPS XML 解析失败: {exc}") from exc

    @staticmethod
    def _extract_total(root: ET.Element) -> int | None:
        """从搜索结果中提取总数"""
        for elem in root.iter("{http://ops.epo.org}biblio-search"):
            total = elem.get("total-result-count")
            if total is not None:
                try:
                    return int(total)
                except ValueError:
                    pass
        return None

    def _extract_search_results(self, root: ET.Element) -> list[PatentResult]:
        """从搜索 XML 中提取专利列表
        
        遍历 exchange-document 节点，逐一转换为 PatentResult，跳过无法解析的项。
        """
        results: list[PatentResult] = []
        for doc in root.iter("{http://www.epo.org/exchange}exchange-document"):
            try:
                results.append(self._exchange_doc_to_result(doc))
            except Exception:
                logger.debug("跳过无法解析的 EPO 文档", exc_info=True)
        return results

    def _extract_publication(
        self,
        root: ET.Element,
        fallback_id: str,
    ) -> PatentResult:
        """从出版物 XML 中提取 PatentResult"""
        for doc in root.iter("{http://www.epo.org/exchange}exchange-document"):
            return self._exchange_doc_to_result(doc)
        # 如果没有 exchange-document 节点，返回最小结果
        return PatentResult(
            source=SourceType.EPO_OPS,
            title="",
            patent_id=fallback_id,
            source_url=f"https://worldwide.espacenet.com/patent/search?q={fallback_id}",
        )

    def _extract_family_members(self, root: ET.Element) -> list[PatentResult]:
        """从专利族 XML 中提取成员列表
        
        遍历 family-member 节点，提取其中的 exchange-document 元素。
        """
        members: list[PatentResult] = []
        for member in root.iter("{http://ops.epo.org}family-member"):
            for doc in member.iter("{http://www.epo.org/exchange}exchange-document"):
                try:
                    members.append(self._exchange_doc_to_result(doc))
                except Exception:
                    logger.debug("跳过无法解析的专利族成员", exc_info=True)
        return members

    @staticmethod
    def _exchange_doc_to_result(doc: ET.Element) -> PatentResult:
        """将 EPO exchange-document 节点转换为 PatentResult
        
        处理多语言字段（优先英文），提取标题、摘要、申请人、发明人、分类号等核心信息。
        """
        ns_epo = "{http://www.epo.org/exchange}"

        # 文档号由国家代码、文档号、文件种类组合而成
        country = doc.get("country", "")
        doc_number = doc.get("doc-number", "")
        kind = doc.get("kind", "")
        patent_id = f"{country}{doc_number}{kind}"

        # 标题 (取英文优先，否则取首个可用标题)
        title = ""
        for t in doc.iter(f"{ns_epo}invention-title"):
            lang = t.get("lang", "")
            text = t.text or ""
            if lang == "en" or not title:
                title = text.strip()

        # 摘要处理方式同标题
        abstract = ""
        for ab in doc.iter(f"{ns_epo}abstract"):
            lang = ab.get("lang", "")
            # 摘要可能由多个段落组成
            parts = [p.text for p in ab.iter(f"{ns_epo}p") if p.text]
            text = " ".join(parts)
            if lang == "en" or not abstract:
                abstract = text.strip()

        # 申请人提取
        applicants: list[Applicant] = []
        for app in doc.iter(f"{ns_epo}applicant"):
            name_elem = app.find(f"{ns_epo}name")
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            residence = app.find(f"{ns_epo}residence")
            country_code = None
            if residence is not None:
                c_elem = residence.find(f"{ns_epo}country")
                country_code = c_elem.text if c_elem is not None else None
            if name:
                applicants.append(Applicant(name=name, country=country_code))

        # 发明人提取
        inventors: list[str] = []
        for inv in doc.iter(f"{ns_epo}inventor"):
            name_elem = inv.find(f"{ns_epo}name")
            if name_elem is not None and name_elem.text:
                inventors.append(name_elem.text.strip())

        # IPC 分类号
        ipc_codes: list[str] = []
        for ipc in doc.iter(f"{ns_epo}classification-ipcr"):
            text_elem = ipc.find(f"{ns_epo}text")
            if text_elem is not None and text_elem.text:
                ipc_codes.append(text_elem.text.strip())

        # 公开日期
        pub_date: date | None = None
        for pd in doc.iter(f"{ns_epo}publication-reference"):
            date_elem = pd.find(f".//{ns_epo}date")
            if date_elem is not None and date_elem.text:
                pub_date = _safe_date(date_elem.text)
                break

        # 申请日期
        filing_date: date | None = None
        for ad in doc.iter(f"{ns_epo}application-reference"):
            date_elem = ad.find(f".//{ns_epo}date")
            if date_elem is not None and date_elem.text:
                filing_date = _safe_date(date_elem.text)
                break

        return PatentResult(
            source=SourceType.EPO_OPS,
            title=title,
            patent_id=patent_id,
            publication_date=pub_date,
            filing_date=filing_date,
            applicants=applicants,
            inventors=inventors,
            abstract=abstract or None,
            ipc_codes=ipc_codes,
            source_url=f"https://worldwide.espacenet.com/patent/search?q={patent_id}",
            raw={"country": country, "doc_number": doc_number, "kind": kind},
        )


def _safe_date(value: str | None) -> date | None:
    """安全解析 EPO 日期格式 (YYYYMMDD 或 YYYY-MM-DD)
    
    处理两种常见 EPO 日期格式，失败时返回 None。
    
    Args:
        value: 日期字符串或 None
    
    Returns:
        date 对象，解析失败返回 None
    """
    if not value:
        return None
    value = value.strip()
    try:
        # YYYYMMDD 格式（无分隔符）
        if len(value) == 8 and value.isdigit():
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        # YYYY-MM-DD 或其他 ISO 格式
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None
