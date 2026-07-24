"""Legacy error path and domain-specific compatibility definitions."""

from souwen.common_runtime.errors import SouWenError as SouWenError
from souwen.common_runtime.transport import (
    AuthError as AuthError,
    RateLimitError as RateLimitError,
    SourceUnavailableError as SourceUnavailableError,
)


class ConfigError(SouWenError):
    """配置缺失或无效（如未设置必需的 API Key）

    属性：
        key: 配置项名称（如 'tavily_api_key'）
        service: 相关服务名称（如 'Tavily'）
        register_url: 注册/获取 API Key 的 URL（可选）
    """

    def __init__(self, key: str, service: str, register_url: str | None = None):
        """初始化配置错误

        Args:
            key: 缺失的配置项名称
            service: 所属服务名称
            register_url: 如提供，会在错误信息中附加获取链接
        """
        self.key = key
        self.service = service
        self.register_url = register_url
        msg = f"缺少配置项 '{key}'（{service} 必需）"
        if register_url:
            msg += f"\n注册获取: {register_url}"
        super().__init__(msg)


class LocalCatalogUnavailableError(SourceUnavailableError):
    """A local catalog is missing, empty, corrupt, or schema-incompatible."""

    pass


class ParseError(SouWenError):
    """响应解析失败

    示例场景：
        - JSON 格式错误
        - 数据源返回意外格式
        - 字段缺失或类型不匹配
    """

    pass


class NotFoundError(SouWenError):
    """未找到结果

    示例场景：
        - 搜索关键词无结果
        - 指定 ID 的资源不存在
    """

    pass
