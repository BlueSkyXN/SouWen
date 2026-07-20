/**
 * Helpers for API config values that are safe display strings, not saveable secrets.
 */

const REDACTED_MARKER = '***'

export function isRedactedConfigValue(value: string | null | undefined): boolean {
  return typeof value === 'string' && value.includes(REDACTED_MARKER)
}

export function shouldSubmitConfigValue(
  currentValue: string,
  initialValue: string,
): boolean {
  return currentValue !== initialValue || !isRedactedConfigValue(initialValue)
}
