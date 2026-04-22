/**
 * 登录页面 - 身份认证和服务连接
 *
 * 文件用途：处理用户登录认证流程，支持自动登录（无密码配置）和手动输入密码验证
 *
 * 功能特性：
 *   - 服务器 URL 输入：允许用户指定 API 服务地址
 *   - 密码输入：支持显示/隐藏密码
 *   - 记住密码：localStorage 记录登录状态
 *   - 自动登录：检测无密码配置时自动授权
 *   - 主题切换：登录页面支持 light/dark 模式切换
 *   - 加载状态：提交中禁用按钮并显示加载指示
 *   - 动画反馈：成功时显示动画过渡，失败时震动提示
 *
 * 交互流程：
 *   1. 页面加载时检查已认证状态 → 已认证则重定向首页
 *   2. 尝试自动登录（无密码配置）
 *   3. 若需密码，显示表单等待用户输入
 *   4. 提交验证 → 成功后保存凭证并导航到首页
 *   5. 失败时显示错误 toast 并恢复表单
 */

import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AnimatePresence, m } from 'framer-motion'
import { Search, Moon, Sun, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '@core/stores/authStore'
import { useSkinStore } from '../stores/skinStore'
import { useNotificationStore } from '@core/stores/notificationStore'
import { api } from '@core/services/api'
import { formatError } from '@core/lib/errors'
import styles from './LoginPage.module.scss'

/**
 * LoginPage 主组件
 * 状态：baseUrl/password/remember 表单字段；shake/success/autoConnecting 视觉反馈
 * 关键流程：
 *   1. 已登录 → 直接跳转首页
 *   2. 自动登录尝试：调用 verifyAuth('') 探测无密码服务器，成功则免输入登录
 *   3. 手动登录：调用 health + verifyAuth，失败时触发抖动动画
 */
export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const setRole = useAuthStore((s) => s.setRole)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const { mode, toggleMode } = useSkinStore()
  const addToast = useNotificationStore((s) => s.addToast)

  const [baseUrl, setBaseUrl] = useState(() => {
    const saved = localStorage.getItem('souwen_baseUrl') ?? sessionStorage.getItem('souwen_baseUrl')
    return saved ?? window.location.origin
  })
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [remember, setRemember] = useState(
    () => localStorage.getItem('souwen_remember') === 'true',
  )
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const [success, setSuccess] = useState(false)
  const [autoConnecting, setAutoConnecting] = useState(true)

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

  // Auto-login when server has no password configured
  useEffect(() => {
    let cancelled = false
    async function tryAutoLogin() {
      const url = baseUrl.replace(/\/+$/, '')
      try {
        const health = await api.health(url)
        await api.verifyAuth(url, '')
        if (cancelled) return
        setAuth(url, '', health.version, remember)
        try { const whoami = await api.whoami(); setRole(whoami) } catch { /* non-critical */ }
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

  /**
   * 处理登录表单提交
   * 1. 规范化 baseUrl（去除尾部斜杠）
   * 2. 调用 health 获取版本信息
   * 3. 调用 verifyAuth 验证密码
   * 4. 成功后保存凭证、显示 toast、延迟 400ms 等待动画后跳转
   * 5. 失败时触发 shake 动画 + 错误 toast
   */
  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setLoading(true)
      try {
        const url = baseUrl.replace(/\/+$/, '')
        const health = await api.health(url)
        await api.verifyAuth(url, password)
        setAuth(url, password, health.version, remember)
        try { const whoami = await api.whoami(); setRole(whoami) } catch { /* non-critical */ }
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
    [baseUrl, password, remember, setAuth, setRole, addToast, navigate, t],
  )

  // Show a brief loading state while attempting auto-login
  if (autoConnecting) {
    return (
      <div className={styles.page}>
        <div className={styles.gridBg} />
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, zIndex: 1 }}
        >
          <Loader2 size={32} className={styles.spinner} style={{ color: 'var(--primary)' }} />
          <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>{t('login.autoConnecting')}</span>
        </m.div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.gridBg} />

      <div className={styles.themeToggle}>
        <button
          className={styles.themeBtn}
          onClick={toggleMode}
          aria-label={mode === 'light' ? t('login.darkMode') : t('login.lightMode')}
        >
          <AnimatePresence mode="wait" initial={false}>
            <m.span
              key={mode}
              initial={{ opacity: 0, rotate: -90, scale: 0.5 }}
              animate={{ opacity: 1, rotate: 0, scale: 1 }}
              exit={{ opacity: 0, rotate: 90, scale: 0.5 }}
              transition={{ duration: 0.2 }}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              {mode === 'light' ? <Moon size={18} /> : <Sun size={18} />}
            </m.span>
          </AnimatePresence>
        </button>
      </div>

      <m.div
        initial={{ opacity: 0, scale: 0.96, y: 24 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 280, damping: 24 }}
        style={{ width: '100%', maxWidth: 420, zIndex: 1 }}
      >
        <div
          className={`${styles.card} ${shake ? styles.cardShake : ''} ${success ? styles.cardSuccess : ''}`}
        >
          <div className={styles.logo}>
            <Search size={28} />
          </div>
          <h1 className={styles.title}>{t('app.name')}</h1>
          <p className={styles.subtitle}>{t('app.subtitle')}</p>

          <form onSubmit={handleSubmit}>
            <div className={styles.formGroup}>
              <label>{t('login.serverUrl')}</label>
              <input
                className={styles.input}
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:8000"
                required
              />
            </div>

            <div className={styles.formGroup}>
              <label>{t('login.password')}</label>
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
                  aria-label={showPw ? t('login.hidePassword', 'Hide password') : t('login.showPassword', 'Show password')}
                >
                  <AnimatePresence mode="wait" initial={false}>
                    <m.span
                      key={showPw ? 'hide' : 'show'}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.15 }}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
                      {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                    </m.span>
                  </AnimatePresence>
                </button>
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
              className={`btn btn-primary btn-block ${styles.submitBtn}`}
              disabled={loading || success}
            >
              {loading ? (
                <>
                  <Loader2 size={18} className={styles.spinner} />
                  {t('login.connecting')}
                </>
              ) : (
                t('login.connect')
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
