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

  static fromResponse(status: number, body: string): AppError {
    const isAuth = status === 401 || status === 403
    return new AppError(body || `HTTP ${status}`, status, isAuth)
  }

  static network(cause?: unknown): AppError {
    const msg = cause instanceof Error ? cause.message : '网络连接失败'
    return new AppError(msg, 0, false, true)
  }
}

export function formatError(err: unknown): string {
  if (err instanceof AppError) return err.message
  if (err instanceof Error) return err.message
  return '未知错误'
}
