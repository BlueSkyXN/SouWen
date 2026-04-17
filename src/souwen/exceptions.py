"""SouWen 自定义异常体系

文件用途：
    定义 SouWen 所有自定义异常类，
    用于区分不同错误场景（配置错误、鉴权失败、限流、数据源不可用等）。

异常清单：
    SouWenError（基类）
        - 功能：所有 SouWen 异常的基类
        - 关键：所有业务异常应继承此类
    
    ConfigError（子类）
        - 功能：配置缺失或无效（如未设置必需的 API Key）
        - 入参：key (str) 配置项名称, service (str) 服务名, register_url (str|None) 注册获取链接
        - 出参：带有友好提示的异常信息
    
    AuthError（子类）
        - 功能：鉴权失败（Token 过期、Key 无效等）
    
    RateLimitError（子类）
        - 功能：限流触发，包含重试等待时间
        - 入参：message (str) 错误信息, retry_after (float|None) 建议重试等待秒数
        - 关键属性：retry_after 时间戳
    
    SourceUnavailableError（子类）
        - 功能：数据源不可用（服务宕机、网络错误等）
    
    ParseError（子类）
        - 功能：响应解析失败
    
    NotFoundError（子类）
        - 功能：未找到结果

模块依赖：
    - 标准库 Exception（无外部依赖）
"""


class SouWenError(Exception):
    """SouWen 基础异常"""

    pass


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
