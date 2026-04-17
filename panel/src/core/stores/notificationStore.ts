/**
 * 文件用途：通知/Toast 全局状态存储，使用 Zustand 管理应用级消息队列与自动清理
 *
 * 接口/函数清单：
 *     NotificationState（接口）
 *         - 功能：通知状态树
 *         - 字段：
 *           - toasts Toast[] 当前展示的 toast 列表
 *           - addToast(type: ToastType, message: string) -> void 添加通知
 *           - removeToast(id: string) -> void 移除通知
 *
 *     useNotificationStore（Zustand hook）
 *         - 功能：全局通知状态存储 hook
 *         - 用法：const { toasts, addToast } = useNotificationStore()
 *
 * 关键逻辑：
 *
 *   addToast 流程：
 *     1. 生成递增的数值 ID 并转换为字符串（确保唯一）
 *     2. 创建 Toast 对象（id, type, message）并追加到列表
 *     3. 启动 4 秒倒计时，自动移除该通知（防止屏幕堆积）
 *
 *   removeToast 流程：
 *     1. 过滤掉指定 ID 的 toast，更新列表
 *
 * 模块依赖：
 *     - zustand: 状态管理库
 *     - ../types: Toast、ToastType 类型定义
 */

import { create } from 'zustand'
import type { Toast, ToastType } from '../types'

/**
 * 通知状态树接口
 */
interface NotificationState {
  toasts: Toast[]
  addToast: (type: ToastType, message: string) => void
  removeToast: (id: string) => void
}

/**
 * 通知/Toast 全局状态存储
 * 管理应用级消息队列，支持自动消失
 */
export const useNotificationStore = create<NotificationState>()((set, get) => {
  let _id = 0
  return {
    toasts: [],

    /**
     * 添加通知
     * 生成唯一 ID，启动 4 秒自动移除倒计时
     */
    addToast: (type, message) => {
      const id = String(++_id)
      set({ toasts: [...get().toasts, { id, type, message }] })
      setTimeout(() => {
        get().removeToast(id)
      }, 4000)
    },

    /**
     * 移除指定 ID 的通知
     */
    removeToast: (id) => {
      set({ toasts: get().toasts.filter((t) => t.id !== id) })
    },
  }
})
