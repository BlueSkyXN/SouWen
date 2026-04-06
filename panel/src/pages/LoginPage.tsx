import { useState, useCallback, type FormEvent } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { useNotificationStore } from '../stores/notificationStore'
import { api } from '../services/api'
import styles from './LoginPage.module.scss'

export function LoginPage() {
  const setAuth = useAuthStore((s) => s.setAuth)
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

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setLoading(true)
      try {
        const url = baseUrl.replace(/\/+$/, '')
        if (remember) {
          localStorage.setItem('souwen_remember', 'true')
        } else {
          localStorage.removeItem('souwen_remember')
        }

        const health = await api.health(url)
        setAuth(url, password, health.version)
        addToast('success', `连接成功 — SouWen v${health.version}`)
      } catch (err) {
        addToast('error', `连接失败: ${err instanceof Error ? err.message : '未知错误'}`)
      } finally {
        setLoading(false)
      }
    },
    [baseUrl, password, remember, setAuth, addToast],
  )

  return (
    <div className={styles.page}>
      <div className={styles.themeToggle}>
        <button className={styles.themeBtn} onClick={toggleTheme}>
          {theme === 'light' ? '🌙' : '☀️'}
        </button>
      </div>
      <div className={styles.card}>
        <div className={styles.logo}>🔍</div>
        <h1 className={styles.title}>SouWen 搜文</h1>
        <p className={styles.subtitle}>学术搜索聚合引擎 · 管理面板</p>

        <form onSubmit={handleSubmit}>
          <div className={styles.formGroup}>
            <label>服务地址</label>
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
            <label>访问密码</label>
            <div className={styles.inputGroup}>
              <input
                className={styles.input}
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="留空表示无密码"
              />
              <button
                type="button"
                className={styles.togglePw}
                onClick={() => setShowPw((v) => !v)}
              >
                {showPw ? '🙈' : '👁️'}
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
            <label htmlFor="remember">记住连接信息</label>
          </div>

          <button
            type="submit"
            className={`btn btn-primary btn-block ${styles.submitBtn}`}
            disabled={loading}
          >
            {loading ? '连接中...' : '连接'}
          </button>
        </form>
      </div>
    </div>
  )
}
