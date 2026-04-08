import { create } from 'zustand'
import type { Toast, ToastType } from '../types'

interface NotificationState {
  toasts: Toast[]
  addToast: (type: ToastType, message: string) => void
  removeToast: (id: string) => void
}

export const useNotificationStore = create<NotificationState>()((set, get) => {
  let _id = 0
  return {
    toasts: [],

    addToast: (type, message) => {
      const id = String(++_id)
      set({ toasts: [...get().toasts, { id, type, message }] })
      setTimeout(() => {
        get().removeToast(id)
      }, 4000)
    },

    removeToast: (id) => {
      set({ toasts: get().toasts.filter((t) => t.id !== id) })
    },
  }
})
