import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Search, Moon, Sun, Eye, EyeOff } from 'lucide-react'
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
        setAuth(url, password, health.version, remember)
        addToast('success', t('login.success', { version: health.version }))
        navigate('/', { replace: true })
      } catch (err) {
        addToast('error', t('login.failed', { message: formatError(err) }))
      } finally {
        setLoading(false)
      }
    },
    [baseUrl, password, remember, setAuth, addToast, navigate, t],
  )

  return (
    <div className={styles.page}>
      <div className={styles.themeToggle}>
        <button className={styles.themeBtn} onClick={toggleTheme}>
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
      </div>
      <m.div
        className={styles.card}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className={styles.logo}>
          <Search size={32} />
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
              >
                {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
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
            disabled={loading}
          >
            {loading ? t('login.connecting') : t('login.connect')}
          </button>
        </form>
      </m.div>
    </div>
  )
}
