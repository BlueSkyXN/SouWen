import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AnimatePresence, m } from 'framer-motion'
import { Search, Moon, Sun, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { useNotificationStore } from '../stores/notificationStore'
import { api } from '../services/api'
import { formatError } from '../lib/errors'
import styles from './LoginPage.module.scss'

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const { theme, toggleTheme } = useThemeStore()
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

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true })
    }
  }, [isAuthenticated, navigate])

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

  return (
    <div className={styles.page}>
      <div className={styles.gridBg} />

      <div className={styles.themeToggle}>
        <button
          className={styles.themeBtn}
          onClick={toggleTheme}
          aria-label={theme === 'light' ? t('login.darkMode') : t('login.lightMode')}
        >
          <AnimatePresence mode="wait" initial={false}>
            <m.span
              key={theme}
              initial={{ opacity: 0, rotate: -90, scale: 0.5 }}
              animate={{ opacity: 1, rotate: 0, scale: 1 }}
              exit={{ opacity: 0, rotate: 90, scale: 0.5 }}
              transition={{ duration: 0.2 }}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
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
    </div>
  )
}
