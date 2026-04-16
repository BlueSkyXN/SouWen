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

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
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
