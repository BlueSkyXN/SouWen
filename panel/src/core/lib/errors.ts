/**
 * 文件用途：应用级错误处理，提供自定义错误类与格式化工具
 *
 * 类/函数清单：
 *     AppError（类）
 *         - 功能：统一应用错误类，扩展 Error 并分类错误类型
 *         - 构造参数：
 *           - message string 错误消息
 *           - status number HTTP 状态码或 0（网络错误），默认 0
 *           - isAuth boolean 是否为认证/授权错误，默认 false
 *           - isNetwork boolean 是否为网络错误，默认 false
 *         - 属性：status, isAuth, isNetwork
 *
 *     AppError.fromResponse（静态方法）
 *         - 功能：从 HTTP 响应创建错误实例
 *         - 输入：status 响应码，body 响应体文本
 *         - 输出：AppError 实例（自动检测 401 为认证错误）
 *         - 逻辑：状态码 401 时，isAuth 标记为 true；空 body 时用 HTTP 状态信息作消息
 *
 *     AppError.network（静态方法）
 *         - 功能：创建网络错误实例
 *         - 输入：cause 可选的原因对象（Error 或其他）
 *         - 输出：AppError 实例（isNetwork 为 true）
 *         - 逻辑：如果 cause 是 Error，使用其 message；否则调用 i18n 获取默认网络错误文本
 *
 *     formatError（函数）
 *         - 功能：将任意错误对象格式化为用户友好的字符串
 *         - 输入：err 错误对象（AppError、Error、其他）
 *         - 输出：错误消息字符串
 *         - 逻辑：优先返回 AppError 消息 → Error 消息 → i18n 默认未知错误文本
 *
 * 模块依赖：
 *     - ../i18n: 国际化模块，提供默认错误文本
 */

import i18n from '../i18n'

/**
 * AppError 自定义错误类
 * 为应用内所有错误提供统一接口，支持错误分类（认证、网络等）
 */
export class AppError extends Error {
  constructor(
    message: string,
    public readonly status: number = 0,
    public readonly isAuth: boolean = false,
    public readonly isNetwork: boolean = false,
  ) {
    super(message)
    this.name = 'AppError'
  }

  /**
   * 从 HTTP 响应创建 AppError 实例
   * 自动判断 401 为认证错误，使用响应状态信息作为备用消息
   */
  static fromResponse(status: number, body: string): AppError {
    const isAuth = status === 401
    return new AppError(body || `HTTP ${status}`, status, isAuth)
  }

  /**
   * 创建网络错误实例
   * 用于 fetch 超时、连接失败等网络级异常
   */
  static network(cause?: unknown): AppError {
    const msg = cause instanceof Error ? cause.message : i18n.t('common.networkError')
    return new AppError(msg, 0, false, true)
  }
}

/**
 * 格式化错误为可显示的字符串
 * 处理 AppError、标准 Error 及其他值，提供一致的错误消息输出
 */
export function formatError(err: unknown): string {
  if (err instanceof AppError) return err.message
  if (err instanceof Error) return err.message
  return i18n.t('common.unknownError')
}
