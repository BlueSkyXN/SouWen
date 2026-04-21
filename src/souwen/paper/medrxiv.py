"""medRxiv Content API 客户端

官方文档: https://api.biorxiv.org/
鉴权: 无需 Key
限流: 无硬限制，建议 1 req/s
返回: JSON

文件用途：medRxiv 医学预印本搜索客户端，复用与 bioRxiv 完全相同的 API 端点。
medRxiv 专注于医学、临床、公共卫生等生物医学领域预印本。

函数/类清单：
    MedrxivClient（类）
        - 功能：medRxiv Content API v2 客户端，与 BiorxivClient 共享全部逻辑，
               仅服务器标识符和 SourceType 不同
        - 继承：BiorxivClient（覆盖 _SERVER / _SOURCE_TYPE 类属性）

    search(query: str, max_results: int, days: int) -> SearchResponse
        - 功能：获取最近 days 天内的 medRxiv 预印本（继承自 BiorxivClient）

    search_by_date(start_date: str, end_date: str, max_results: int) -> SearchResponse
        - 功能：按精确日期范围检索 medRxiv 预印本（继承自 BiorxivClient）

模块依赖：
    - BiorxivClient: 复用所有 API 调用和解析逻辑
    - SourceType.MEDRXIV: medRxiv 专属数据源标识
"""

from __future__ import annotations

from souwen.models import SourceType
from souwen.paper.biorxiv import BiorxivClient


class MedrxivClient(BiorxivClient):
    """medRxiv 医学预印本搜索客户端。

    复用 BiorxivClient 的全部实现，仅将 server 标识符替换为 ``medrxiv``，
    使 API 请求和论文 URL 自动指向 medRxiv 服务器。
    """

    _SERVER: str = "medrxiv"
    _SOURCE_TYPE: SourceType = SourceType.MEDRXIV
