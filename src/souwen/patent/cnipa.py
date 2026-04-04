"""CNIPA 中国国家知识产权局客户端

通过中国专利信息中心 (CNIPR) 开放平台访问中国专利数据，OAuth 2.0 鉴权。
注册地址: https://open.cnipr.com/
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from souwen.config import get_config
from souwen.exceptions import ConfigError, NotFoundError, ParseError
from souwen.http_client import OAuthClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)


class CnipaClient:
    """CNIPA 中国国家知识产权局客户端

    访问中国专利全文数据，支持检索、详情、全文获取。
    使用 OAuth 2.0 Client Credentials 鉴权。

    Attributes:
        BASE_URL: CNIPR 开放平台基础地址
        TOKEN_URL: OAuth 2.0 令牌端点
    """

    BASE_URL = "https://open.cnipr.com"
    TOKEN_URL = "https://open.cnipr.com/oauth/token"

    def __init__(self) -> None:
        cfg = get_config()
        if not cfg.cnipa_client_id or not cfg.cnipa_client_secret:
            raise ConfigError(
                key="cnipa_client_id / cnipa_client_secret",
                service="CNIPA (CNIPR 开放平台)",
                register_url="https://open.cnipr.com/",
            )
        self._http = OAuthClient(
            base_url=self.BASE_URL,
            token_url=self.TOKEN_URL,
            client_id=cfg.cnipa_client_id,
            client_secret=cfg.cnipa_client_secret,
        )
        self._limiter = TokenBucketLimiter(rate=2.0, burst=5)

    async def __aenter__(self) -> CnipaClient:
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
        query: str,
        per_page: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """搜索中国专利

        Args:
            query: 检索表达式 (支持 CNIPA 检索语法)
            per_page: 每页结果数
            offset: 偏移量

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            "/api/search",
            params={
                "q": query,
                "rows": per_page,
                "start": offset,
            },
        )
        data = self._parse_json(resp)

        results_raw = data.get("results", data.get("data", []))
        patents = [self._to_patent_result(item) for item in results_raw]

        return SearchResponse(
            query=query,
            source=SourceType.CNIPA,
            total_results=data.get("total", data.get("totalCount")),
            results=patents,
            page=(offset // per_page) + 1 if per_page else 1,
            per_page=per_page,
        )

    async def get_patent(self, publication_number: str) -> PatentResult:
        """获取专利详情

        Args:
            publication_number: 公开号，例如 ``"CN115000000A"``

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/api/patent/{publication_number}",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {publication_number} 未找到")

        data = self._parse_json(resp)
        result_data = data.get("data", data)
        if not result_data:
            raise NotFoundError(f"专利 {publication_number} 未找到")
        return self._to_patent_result(result_data)

    async def get_fulltext(self, publication_number: str) -> dict[str, Any]:
        """获取专利全文

        Args:
            publication_number: 公开号

        Returns:
            包含说明书、权利要求书等全文内容的字典

        Raises:
            NotFoundError: 未找到该专利全文
        """
        await self._limiter.acquire()
        resp = await self._http.get(
            f"/api/patent/{publication_number}/fulltext",
        )
        if resp.status_code == 404:
            raise NotFoundError(f"专利 {publication_number} 全文未找到")

        data = self._parse_json(resp)
        return data.get("data", data)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(resp: httpx.Response) -> dict[str, Any]:
        """解析 JSON 响应"""
        try:
            return resp.json()
        except Exception as exc:
            raise ParseError(f"CNIPA 响应 JSON 解析失败: {exc}") from exc

    @staticmethod
    def _to_patent_result(raw: dict[str, Any]) -> PatentResult:
        """将 CNIPA 原始数据转换为 PatentResult"""
        patent_id = raw.get(
            "publicationNumber",
            raw.get("publication_number", raw.get("pn", "")),
        )
        app_number = raw.get(
            "applicationNumber",
            raw.get("application_number", raw.get("an")),
        )

        # 申请人
        applicants: list[Applicant] = []
        raw_applicants = raw.get("applicants", raw.get("申请人", []))
        if isinstance(raw_applicants, str):
            # 中文数据源有时以分号分隔
            raw_applicants = [a.strip() for a in raw_applicants.split(";") if a.strip()]
        for a in raw_applicants or []:
            name = a if isinstance(a, str) else a.get("name", a.get("姓名", ""))
            country = a.get("country") if isinstance(a, dict) else None
            if name:
                applicants.append(Applicant(name=name, country=country))

        # 发明人
        raw_inventors = raw.get("inventors", raw.get("发明人", []))
        inventors: list[str] = []
        if isinstance(raw_inventors, str):
            inventors = [i.strip() for i in raw_inventors.split(";") if i.strip()]
        else:
            for inv in raw_inventors or []:
                name = inv if isinstance(inv, str) else inv.get("name", "")
                if name:
                    inventors.append(name)

        # IPC / CPC
        ipc_raw = raw.get("ipcCodes", raw.get("ipc", []))
        ipc_codes: list[str] = (
            [i.strip() for i in ipc_raw.split(";") if i.strip()]
            if isinstance(ipc_raw, str)
            else [c for c in ipc_raw if isinstance(c, str)]
        )

        cpc_raw = raw.get("cpcCodes", raw.get("cpc", []))
        cpc_codes: list[str] = (
            [c.strip() for c in cpc_raw.split(";") if c.strip()]
            if isinstance(cpc_raw, str)
            else [c for c in cpc_raw if isinstance(c, str)]
        )

        return PatentResult(
            source=SourceType.CNIPA,
            title=raw.get("title", raw.get("发明名称", "")),
            patent_id=patent_id,
            application_number=app_number,
            publication_date=_safe_date(
                raw.get("publicationDate", raw.get("publication_date"))
            ),
            filing_date=_safe_date(
                raw.get("filingDate", raw.get("filing_date"))
            ),
            applicants=applicants,
            inventors=inventors,
            abstract=raw.get("abstract", raw.get("摘要")),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            legal_status=raw.get("legalStatus", raw.get("legal_status")),
            source_url=f"https://open.cnipr.com/patent/{patent_id}" if patent_id else "",
            raw=raw,
        )


def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串"""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
