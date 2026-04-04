"""SouWen 自定义异常体系"""


class SouWenError(Exception):
    """SouWen 基础异常"""
    pass


class ConfigError(SouWenError):
    """配置缺失或无效（如未设置必需的 API Key）"""
    
    def __init__(self, key: str, service: str, register_url: str | None = None):
        self.key = key
        self.service = service
        self.register_url = register_url
        msg = f"缺少配置项 '{key}'（{service} 必需）"
        if register_url:
            msg += f"\n注册获取: {register_url}"
        super().__init__(msg)


class AuthError(SouWenError):
    """鉴权失败（Token 过期、Key 无效等）"""
    pass


class RateLimitError(SouWenError):
    """限流触发，包含重试等待时间"""
    
    def __init__(self, message: str = "请求过于频繁", retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(message)


class SourceUnavailableError(SouWenError):
    """数据源不可用（服务宕机、网络错误等）"""
    pass


class ParseError(SouWenError):
    """响应解析失败"""
    pass


class NotFoundError(SouWenError):
    """未找到结果"""
    pass
