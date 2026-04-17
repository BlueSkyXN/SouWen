/**
 * 文件用途：国际化（i18n）模块，初始化 i18next 与 React 18 集成
 *
 * 函数/配置清单：
 *     i18n 配置与初始化
 *         - 功能：配置 i18next 实例，加载中文翻译资源，设置语言与回退策略
 *         - 依赖：i18next（核心库）、react-i18next（React 集成）、zh-CN.json（中文翻译字典）
 *         - 关键配置：
 *           - resources：翻译资源树（当前仅加载 zh-CN）
 *           - lng：活跃语言代码，默认 zh-CN
 *           - fallbackLng：当翻译缺失时的回退语言，设为 zh-CN 确保始终有可用翻译
 *           - interpolation.escapeValue: false （因翻译来自静态 JSON，不含用户输入，无需转义防止 XSS）
 *
 * 模块依赖：
 *     - i18next: 国际化框架核心
 *     - react-i18next: React 组件与 Hook 集成（useTranslation）
 *     - ./zh-CN.json: 简体中文翻译字典
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhCN from './zh-CN.json'

i18n.use(initReactI18next).init({
  resources: { 'zh-CN': { translation: zhCN } },
  lng: 'zh-CN',
  fallbackLng: 'zh-CN',
  // 安全配置：翻译来自静态 JSON，非用户输入，不需转义防 XSS
  interpolation: { escapeValue: false },
})

export default i18n
