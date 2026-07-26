import { ApiServiceBase } from './_base'
import type { ConfigResponse, DoctorResponse } from '../types'

/** The only handwritten Panel transport is the read-only admin/control plane. */
class AdminClient extends ApiServiceBase {
  getConfig(): Promise<ConfigResponse> {
    return this.request<ConfigResponse>('/api/v1/admin/config', { headers: this.headers() })
  }

  getDoctor(): Promise<DoctorResponse> {
    return this.request<DoctorResponse>('/api/v1/admin/doctor', { headers: this.headers() })
  }
}

export const adminClient = new AdminClient()
