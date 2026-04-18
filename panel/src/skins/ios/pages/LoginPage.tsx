/**
 * 文件用途：iOS 皮肤的登录页面，处理用户身份验证和服务器连接
 *
 * 组件/函数清单：
 *   LoginPage（函数组件）
 *     - 功能：提供登录表单，支持服务器 URL 和密码输入，自动登录（无密码服务器），记住密码选项
 *     - State 状态：
 *       baseUrl (string) 服务器 URL，从 localStorage/sessionStorage/window.location 恢复
 *       password (string) 输入的密码
 *       showPw (boolean) 是否显示密码文本
 *       remember (boolean) 是否记住密码
 *       loading (boolean) 登录中状态
 *       shake (boolean) 登录失败时的抖动动画
 *       success (boolean) 登录成功状态
 *       autoConnecting (boolean) 首次自动连接中状态
 *     - 关键钩子：useAuthStore 获取认证操作, useNotificationStore 显示提示信息, useNavigate 跳转
 *     - 关键逻辑：自动登录、手动表单提交、眼睛图标切换密码可见性、成功后延迟导航
 *
 * 模块依赖：
 *   - react-router-dom: useNavigate 路由导航
 *   - react-i18next: useTranslation 国际化
 *   - framer-motion: 动画库（表单进入、加载中、成功状态）
 *   - lucide-react: Eye/EyeOff/Loader2 图标
 *   - @core/stores: authStore、notificationStore
 *   - @core/services/api: api.health、api.verifyAuth
 *   - LoginPage.module.scss: 页面样式
 */

import { useState, useCallback, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AnimatePresence, m } from 'framer-motion'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { useNotificationStore } from '@core/stores/notificationStore'
import { api } from '@core/services/api'
import { formatError } from '@core/lib/errors'
import styles from './LoginPage.module.scss'

// LoginPage 组件 - 登录界面
// 支持自动登录（无密码服务器）和手动密码验证两种认证流程
export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const addToast = useNotificationStore((s) => s.addToast)

  // 从本地存储恢复服务器 URL
  const [baseUrl, setBaseUrl] = useState(() => {
    const saved = localStorage.getItem('souwen_baseUrl') ?? sessionStorage.getItem('souwen_baseUrl')
    return saved ?? window.location.origin
  })
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  // 从本地存储恢复"记住密码"状态
  const [remember, setRemember] = useState(
    () => localStorage.getItem('souwen_remember') === 'true',
  )
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const [success, setSuccess] = useState(false)
  const [autoConnecting, setAutoConnecting] = useState(true)

  // 自动登录流程：无密码服务器，则直接验证成功
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  useEffect(() => {
    let cancelled = false
    async function tryAutoLogin() {
      const url = baseUrl.replace(/\/+$/, '')
      try {
        const health = await api.health(url)
        await api.verifyAuth(url, '')
        if (cancelled) return
        setAuth(url, '', health.version, remember)
        navigate('/', { replace: true })
      } catch {
        // Server requires a password — show the login form
      } finally {
        if (!cancelled) setAutoConnecting(false)
      }
    }
    void tryAutoLogin()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 手动提交登录表单
  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setLoading(true)
      try {
        const url = baseUrl.replace(/\/+$/, '')
        const health = await api.health(url)
        await api.verifyAuth(url, password)
        setAuth(url, password, health.version, remember)
        setSuccess(true)
        addToast('success', t('login.success', { version: health.version }))
        await new Promise((r) => setTimeout(r, 400))
        navigate('/', { replace: true })
      } catch (err) {
        setShake(true)
        setTimeout(() => setShake(false), 500)
        addToast('error', t('login.failed', { message: formatError(err) }))
      } finally {
        setLoading(false)
      }
    },
    [baseUrl, password, remember, setAuth, addToast, navigate, t],
  )

  if (autoConnecting) {
    return (
      <div className={styles.page}>
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className={styles.autoConnecting}
        >
          <Loader2 size={28} className={styles.spinner} style={{ color: 'var(--accent)' }} />
          <span>{t('login.autoConnecting')}</span>
        </m.div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <m.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring' as const, stiffness: 300, damping: 26 }}
        style={{ width: '100%', maxWidth: 400, zIndex: 1, padding: '0 16px' }}
      >
        <div
          className={`${styles.card} ${shake ? styles.cardShake : ''} ${success ? styles.cardSuccess : ''}`}
        >
          <h1 className={styles.title}>SouWen</h1>
          <p className={styles.subtitle}>{t('app.subtitle')}</p>

          <form onSubmit={handleSubmit}>
            <div className={styles.formGroup}>
              <div className={styles.groupTitle}>{t('login.serverUrl')}</div>
              <div className={styles.groupCard}>
                <input
                  className={styles.input}
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:8000"
                  required
                />
              </div>
            </div>

            <div className={styles.formGroup}>
              <div className={styles.groupTitle}>{t('login.password')}</div>
              <div className={styles.groupCard}>
                <div className={styles.inputGroup}>
                  <input
                    className={styles.input}
                    type={showPw ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t('login.passwordPlaceholder')}
                  />
                  <button
                    type="button"
                    className={styles.togglePw}
                    onClick={() => setShowPw((v) => !v)}
                    aria-label={showPw ? t('login.hidePassword') : t('login.showPassword')}
                  >
                    <AnimatePresence mode="wait" initial={false}>
                      <m.span
                        key={showPw ? 'hide' : 'show'}
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.8 }}
                        transition={{ duration: 0.15 }}
                        style={{ display: 'flex' }}
                      >
                        {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                      </m.span>
                    </AnimatePresence>
                  </button>
                </div>
              </div>
            </div>

            <div className={styles.checkboxRow}>
              <input
                type="checkbox"
                id="remember"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <label htmlFor="remember">{t('login.remember')}</label>
            </div>

            <button
              type="submit"
              className={styles.submitBtn}
              disabled={loading || success}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className={styles.spinner} />
                  {t('login.connecting')}
                </>
              ) : (
                t('login.signIn', 'Sign In')
              )}
            </button>
          </form>
        </div>
      </m.div>
      <div className={styles.loginFooter}>
        <a href="https://github.com/BlueSkyXN/SouWen" target="_blank" rel="noopener noreferrer">SouWen 搜文</a> · @BlueSkyXN · GPLv3
      </div>
    </div>
  )
}
