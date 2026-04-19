/**
 * URL 工具函数
 *
 * 提供 URL 解析和展示相关的实用函数
 */

/**
 * 从完整 URL 中提取域名（去除 www. 前缀）
 *
 * @example extractDomain('https://www.nature.com/articles/123') → 'nature.com'
 * @example extractDomain('https://arxiv.org/abs/2301.00001') → 'arxiv.org'
 * @example extractDomain('invalid-url') → 'invalid-url'
 */
export function extractDomain(url: string): string {
  try {
    const hostname = new URL(url).hostname
    return hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
