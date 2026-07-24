"""Stable outbound transport error taxonomy."""

from souwen.common_runtime.errors import SouWenError


class AuthError(SouWenError):
    """鉴权失败（Token 过期、Key 无效等）

    示例场景：
        - HTTP 401 Unauthorized
        - API Key 被拒绝
        - OAuth Token 失效
    """

    pass


class RateLimitError(SouWenError):
    """限流触发，包含重试等待时间

    属性：
        retry_after: 建议重试等待的秒数（来自 Retry-After 响应头或限流策略）
    """

    def __init__(self, message: str = "请求过于频繁", retry_after: float | None = None):
        """初始化限流异常

        Args:
            message: 错误信息
            retry_after: 建议等待秒数（如有）
        """
        self.retry_after = retry_after
        super().__init__(message)


class SourceUnavailableError(SouWenError):
    """数据源不可用（服务宕机、网络错误等）

    示例场景：
        - 服务器返回 5xx 错误
        - 网络连接失败
        - DNS 解析失败
    """

    pass
