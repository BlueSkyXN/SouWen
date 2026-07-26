export interface HealthResponse {
  status: string
  version: string
  source_sha?: string | null
}

export type UserRole = 'guest' | 'user' | 'admin'

export interface WhoamiResponse {
  role: UserRole
  features: Record<string, boolean | string>
  guest_enabled: boolean
  user_password_set: boolean
  admin_password_set: boolean
  admin_open: boolean
}

export type ConfigResponse = Record<string, unknown>
export type DoctorResponse = Record<string, unknown>
