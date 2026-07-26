"""Bilibili 自定义异常

聚合方法（search, get_popular 等）不抛异常，降级为空结果；
查找方法（get_video_details, get_user_info 等）抛对应异常。
"""

from __future__ import annotations


class BilibiliError(Exception):
    """Bilibili API 通用错误基类"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bilibili API error {code}: {message}")


class BilibiliNotFound(BilibiliError):
    """资源不存在（-404, 62002, 62004）"""


class BilibiliAuthRequired(BilibiliError):
    """需要登录（-101）"""


class BilibiliRateLimited(BilibiliError):
    """被限流（-412, 412）"""


class BilibiliRiskControl(BilibiliError):
    """风控拦截（-352）"""


# Bilibili 错误码 → 异常类映射
_ERROR_CODE_MAP: dict[int, type[BilibiliError]] = {
    -101: BilibiliAuthRequired,
    -404: BilibiliNotFound,
    62002: BilibiliNotFound,
    62004: BilibiliNotFound,
    -412: BilibiliRateLimited,
    412: BilibiliRateLimited,
    -352: BilibiliRiskControl,
}


def raise_for_code(code: int, message: str) -> None:
    """根据 Bilibili 错误码抛出对应异常

    Args:
        code: Bilibili API 返回的 code 字段
        message: Bilibili API 返回的 message 字段

    Raises:
        BilibiliNotFound / BilibiliAuthRequired / BilibiliRateLimited /
        BilibiliRiskControl / BilibiliError
    """
    exc_cls = _ERROR_CODE_MAP.get(code, BilibiliError)
    raise exc_cls(code, message)
