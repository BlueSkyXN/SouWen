import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { HashRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from 'react-router'
import { Database, FileSearch, LogOut, Moon, Network, Search, Sparkles, Sun, type LucideIcon } from 'lucide-react'
import { SEARCH_DOMAINS, SouWenClient, type FetchBatch, type LLMSearchResult, type SearchPage } from '@core/sdk'
import { useSouWenClient } from '@core/sdk-client'
import { formatError } from '@core/lib/errors'
import { adminClient } from '@core/services/admin-client'
import { useAuthStore } from '@core/stores/authStore'
import styles from './CalmPrecisionApp.module.scss'

type DataState<T> = { status: 'idle' | 'loading' | 'success' | 'error'; data?: T; error?: string }
type RequestFor<T extends 'search' | 'llmSearch' | 'fetch'> = Parameters<SouWenClient[T]>[0]
type Item = Record<string, unknown>

const SECRET_KEY = /(?:token|secret|password|api[_-]?key|authorization|cookie|credential)/i

export function redactForDisplay(value: unknown, key = ''): unknown {
  if (SECRET_KEY.test(key)) return '[redacted]'
  if (Array.isArray(value)) return value.map((entry) => redactForDisplay(entry))
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value as Item).map(([childKey, childValue]) => [childKey, redactForDisplay(childValue, childKey)]))
  return value
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Keep Settings focused on safe product posture instead of echoing the full server config. */
export function projectSettingsForDisplay(value: unknown): Record<string, unknown> {
  const config = isRecord(value) ? value : {}
  const sources = isRecord(config.sources) ? config.sources : {}
  const gateways = isRecord(config.llm_search_gateways) ? config.llm_search_gateways : {}
  const gatewayCount = Object.keys(gateways).length
  return {
    access: {
      guest_enabled: config.guest_enabled === true,
      docs_enabled: config.expose_docs === true,
      cors_origin_count: Array.isArray(config.cors_origins) ? config.cors_origins.length : 0,
      trusted_proxy_count: Array.isArray(config.trusted_proxies) ? config.trusted_proxies.length : 0,
    },
    providers: {
      configured_source_count: Object.keys(sources).length,
      llm_gateway_count: gatewayCount,
    },
    llm_search: {
      gateway_declared: gatewayCount > 0,
      availability_source: 'Providers',
    },
  }
}

function Status({ state, name }: { state: DataState<unknown>; name: string }) {
  if (state.status === 'loading') return <p className={`${styles.status} ${styles.loading}`} role="status">正在请求{name}…</p>
  if (state.status === 'error') return <p className={`${styles.status} ${styles.error}`} role="alert">{state.error}</p>
  if (state.status === 'success') return <p className={`${styles.status} ${styles.success}`} role="status">{name}已更新。</p>
  return null
}

function Header({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: ReactNode }) {
  return <header className={styles.pageHeader}><div><p className={styles.eyebrow}>{eyebrow}</p><h1 className={styles.title}>{title}</h1><p className={styles.description}>{description}</p></div>{children}</header>
}

function useLatestRequest<T>() {
  const current = useRef<AbortController | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      current.current?.abort()
    }
  }, [])

  const cancel = useCallback(() => current.current?.abort(), [])
  const run = useCallback(async (
    request: (signal: AbortSignal) => Promise<T>,
    onSuccess: (value: T) => void,
    onError: (error: unknown) => void,
  ) => {
    current.current?.abort()
    const controller = new AbortController()
    current.current = controller
    try {
      const value = await request(controller.signal)
      if (mounted.current && current.current === controller && !controller.signal.aborted) onSuccess(value)
    } catch (error) {
      if (mounted.current && current.current === controller && !controller.signal.aborted) onError(error)
    } finally {
      if (current.current === controller) current.current = null
    }
  }, [])

  return { cancel, run }
}

function Results({ items }: { items: Item[] }) {
  if (!items.length) return <div className={`${styles.panel} ${styles.empty}`}>本次请求没有可显示的结果。</div>
  return <section className={styles.resultList} aria-live="polite" aria-label="结果">{items.map((item, index) => {
    const title = String(item.title ?? item.title_or_snippet ?? item.target ?? item.id ?? `结果 ${index + 1}`)
    const url = typeof item.url === 'string' ? item.url : typeof item.public_url === 'string' ? item.public_url : typeof item.final_url === 'string' ? item.final_url : undefined
    const body = typeof item.snippet === 'string' ? item.snippet : typeof item.content === 'string' ? item.content : item.error ? JSON.stringify(item.error, null, 2) : ''
    return <article className={`${styles.panel} ${styles.result}`} key={String(item.id ?? item.target ?? index)}>{url ? <a className={styles.resultTitle} href={url} target="_blank" rel="noreferrer">{title}</a> : <strong className={styles.resultTitle}>{title}</strong>}<p className={styles.resultMeta}>{[item.status, item.rank ? `排名 ${item.rank}` : item.provider].filter(Boolean).join(' · ') || '已规范化结果'}</p>{body && <p className={styles.resultBody}>{body}</p>}</article>
  })}</section>
}

function SearchPage() {
  const client = useSouWenClient()
  const request = useLatestRequest<SearchPage>()
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState('paper')
  const [state, setState] = useState<DataState<{ items: Item[] }>>({ status: 'idle' })
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!query.trim()) return; setState({ status: 'loading' })
    void request.run(
      (signal) => client.search({ query: query.trim(), domains: [domain], page: { limit: 20 } } as RequestFor<'search'>, { signal }),
      (data) => setState({ status: 'success', data: data as unknown as { items: Item[] } }),
      (error) => setState({ status: 'error', error: formatError(error) }),
    )
  }
  return <><Header eyebrow="Search" title="搜索" description="选择一个领域，由 Server 的有序默认策略选择一个 Provider；结果只展示可追溯的公共字段。" /><section className={`${styles.panel} ${styles.formPanel}`}><form className={styles.form} onSubmit={submit}><div className={styles.field}><label className={styles.label} htmlFor="search-query">查询</label><input className={styles.input} id="search-query" name="query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} required maxLength={4096} placeholder="输入研究问题、主题或作者" /></div><div className={styles.field}><label className={styles.label} htmlFor="search-domain">领域</label><select className={styles.select} id="search-domain" name="domain" value={domain} onChange={(event) => setDomain(event.target.value)}>{SEARCH_DOMAINS.map((value) => <option key={value} value={value}>{value}</option>)}</select><span className={styles.hint}>一次只接受一个领域；默认 paper 使用部署配置中的 primary Provider。</span></div><div className={styles.formFooter}><span className={styles.hint}>由 generated SouWenClient 发送请求。</span><button className={styles.button} disabled={state.status === 'loading' || !query.trim()} type="submit" aria-busy={state.status === 'loading'}>运行搜索</button></div></form></section><Status state={state} name="搜索结果" />{state.status === 'success' && <Results items={state.data?.items ?? []} />}</>
}

function LlmSearchPage() {
  const client = useSouWenClient()
  const request = useLatestRequest<LLMSearchResult>()
  const [query, setQuery] = useState('')
  const [provider, setProvider] = useState('')
  const [state, setState] = useState<DataState<{ answer?: string | null; evidence: Item[]; items: Item[] }>>({ status: 'idle' })
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!query.trim() || !provider.trim()) return; setState({ status: 'loading' })
    void request.run(
      (signal) => client.llmSearch({ query: query.trim(), providers: [{ id: provider.trim(), kind: 'llm_search' }], strategy: 'single' } as RequestFor<'llmSearch'>, { signal }),
      (data) => setState({ status: 'success', data: data as unknown as { answer?: string | null; evidence: Item[]; items: Item[] } }),
      (error) => setState({ status: 'error', error: formatError(error) }),
    )
  }
  return <><Header eyebrow="LLM Search" title="综合搜索" description="返回结构化来源证据；Provider 支持可验证 synthesis 时同时展示综合回答。" /><section className={`${styles.panel} ${styles.formPanel}`}><form className={styles.form} onSubmit={submit}><div className={styles.field}><label className={styles.label} htmlFor="llm-query">问题</label><textarea className={styles.textarea} id="llm-query" name="query" value={query} onChange={(event) => setQuery(event.target.value)} required maxLength={4096} placeholder="提出一个需要依据的研究问题" /></div><div className={styles.field}><label className={styles.label} htmlFor="llm-provider">Provider ID</label><input className={styles.input} id="llm-provider" name="provider" value={provider} onChange={(event) => setProvider(event.target.value)} required placeholder="从 Providers 页复制 available 的 LLM Search ID" /><span className={styles.hint}>Target runtime 只接受一个已配置 provider，策略固定为 single。</span></div><div className={styles.formFooter}><span className={styles.hint}>预算与认证边界由服务端执行。</span><button className={styles.button} disabled={state.status === 'loading' || !query.trim() || !provider.trim()} type="submit" aria-busy={state.status === 'loading'}>运行 LLM Search</button></div></form></section><Status state={state} name="LLM Search" />{state.status === 'success' && <section className={styles.responseStack} aria-live="polite">{state.data?.answer ? <article className={`${styles.panel} ${styles.answer}`}><h2 className={styles.sectionTitle}>回答</h2><p className={styles.resultBody}>{state.data.answer}</p></article> : <p className={`${styles.panel} ${styles.empty}`}>当前 Provider 返回了结构化证据，但未提供可验证的综合回答。</p>}<Results items={state.data?.evidence ?? state.data?.items ?? []} /></section>}</>
}

function FetchPage() {
  const client = useSouWenClient()
  const request = useLatestRequest<FetchBatch>()
  const [targets, setTargets] = useState('')
  const [state, setState] = useState<DataState<{ items: Item[] }>>({ status: 'idle' })
  async function submit(event: FormEvent) {
    event.preventDefault(); const urls = targets.split(/\n|,/).map((value) => value.trim()).filter(Boolean); if (!urls.length) return
    if (urls.length > 20) {
      request.cancel()
      setState({ status: 'error', error: '最多支持 20 个 URL。' })
      return
    }
    setState({ status: 'loading' })
    void request.run(
      (signal) => client.fetch({ targets: urls, strategy: 'fallback', policy: { respect_robots: true } } as RequestFor<'fetch'>, { signal }),
      (data) => setState({ status: 'success', data: data as unknown as { items: Item[] } }),
      (error) => setState({ status: 'error', error: formatError(error) }),
    )
  }
  return <><Header eyebrow="Fetch" title="网页抓取" description="每行一个 URL，最多 20 个。抓取与 robots 策略全部由服务端执行。" /><section className={`${styles.panel} ${styles.formPanel}`}><form className={styles.form} onSubmit={submit}><div className={styles.field}><label className={styles.label} htmlFor="fetch-targets">URLs</label><textarea className={styles.textarea} id="fetch-targets" name="targets" value={targets} onChange={(event) => setTargets(event.target.value)} required placeholder={'https://example.org/article\nhttps://example.org/report'} /><span className={styles.hint}>仅接受 http/https URL，服务端负责最终校验。</span></div><div className={styles.field}><span className={styles.label}>Provider 策略</span><span className={styles.hint}>Panel 固定使用 fallback；多 Provider fanout 由显式 SDK/API workflow 使用。</span></div><div className={styles.formFooter}><span className={styles.hint}>可用性取决于当前角色和 provider 配置。</span><button className={styles.button} disabled={state.status === 'loading' || !targets.trim()} type="submit" aria-busy={state.status === 'loading'}>开始 Fetch</button></div></form></section><Status state={state} name="Fetch 结果" />{state.status === 'success' && <Results items={state.data?.items ?? []} />}</>
}

function ProvidersPage() {
  const client = useSouWenClient()
  const [state, setState] = useState<DataState<{ items: Item[] }>>({ status: 'idle' })
  async function load() { setState({ status: 'loading' }); try { const data = await client.listProviders(); setState({ status: 'success', data: data as unknown as { items: Item[] } }) } catch (error) { setState({ status: 'error', error: formatError(error) }) } }
  useEffect(() => { void load() }, [client])
  return <><Header eyebrow="Providers" title="Provider 目录" description="展示各 provider 的能力、可用状态和缺失字段，不回显连接配置或密钥。"><button className={styles.secondaryButton} type="button" onClick={() => void load()} disabled={state.status === 'loading'} aria-busy={state.status === 'loading'}>刷新</button></Header><Status state={state} name="Provider 目录" />{state.status === 'success' && (!state.data?.items.length ? <div className={`${styles.panel} ${styles.empty}`}>没有可用 Provider。</div> : <section className={styles.resultList} aria-live="polite">{state.data.items.map((item, index) => <article className={`${styles.panel} ${styles.provider}`} key={String(item.provider ?? index)}><div><h2 className={styles.providerName}>{String(item.provider ?? 'unknown')}</h2><p className={styles.providerMeta}>{Array.isArray(item.capabilities) ? item.capabilities.join(' · ') : '未声明能力'}{Array.isArray(item.missing_fields) && item.missing_fields.length ? ` · 缺失：${item.missing_fields.join(', ')}` : ''}</p></div><span className={`${styles.badge} ${item.availability === 'available' ? styles.badgeAvailable : ''}`}>{String(item.reason ?? item.availability ?? 'unknown')}</span></article>)}</section>)}</>
}

function AdminPage({ kind }: { kind: 'runtime' | 'settings' }) {
  const [state, setState] = useState<DataState<unknown>>({ status: 'idle' })
  const navigate = useNavigate()
  const title = kind === 'runtime' ? '运行状态' : '安全设置摘要'
  async function load() { setState({ status: 'loading' }); try { const data = kind === 'runtime' ? redactForDisplay(await adminClient.getDoctor()) : projectSettingsForDisplay(await adminClient.getConfig()); setState({ status: 'success', data }) } catch (error) { setState({ status: 'error', error: formatError(error) }) } }
  useEffect(() => { void load() }, [kind])
  return <><Header eyebrow={kind === 'runtime' ? 'Runtime' : 'Settings'} title={title} description={kind === 'runtime' ? '只读的运行诊断摘要，仅管理员可见；不会触发联网探测或状态变更。' : '只读的访问策略与配置数量摘要，不回显完整配置或密钥。'}><div className={styles.topbarActions}><button className={styles.secondaryButton} type="button" onClick={() => navigate('/runtime')} aria-pressed={kind === 'runtime'}>Runtime</button><button className={styles.secondaryButton} type="button" onClick={() => navigate('/settings')} aria-pressed={kind === 'settings'}>Settings</button><button className={styles.secondaryButton} type="button" onClick={() => void load()} disabled={state.status === 'loading'} aria-busy={state.status === 'loading'}>刷新</button></div></Header><Status state={state} name={title} />{state.status === 'success' && <section className={`${styles.panel} ${styles.codePanel}`}><pre className={styles.mono} aria-label={`${title} JSON`}>{JSON.stringify(state.data, null, 2)}</pre></section>}</>
}

function Shell() {
  const logout = useAuthStore((state) => state.logout); const role = useAuthStore((state) => state.role)
  const [dark, setDark] = useState(() => document.documentElement.dataset.mode === 'dark')
  const nav: Array<{ to: string; label: string; Icon: LucideIcon }> = [
    { to: '/search', label: 'Search', Icon: Search },
    { to: '/llm-search', label: 'LLM Search', Icon: Sparkles },
    { to: '/fetch', label: 'Fetch', Icon: FileSearch },
    { to: '/providers', label: 'Providers', Icon: Database },
    ...(role === 'admin' ? [{ to: '/runtime', label: 'Runtime / Settings', Icon: Network }] : []),
  ]
  function toggleTheme() { const next = !dark; setDark(next); document.documentElement.dataset.mode = next ? 'dark' : 'light'; localStorage.setItem('souwen_mode', next ? 'dark' : 'light') }
  return <div className={styles.app}><a className={styles.skipLink} href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>跳到主要内容</a><div className={styles.shell}><aside className={styles.sidebar}><div className={styles.brand}><span className={styles.mark}>SW</span><span>SouWen</span></div><nav className={styles.navigation} aria-label="主导航">{nav.map(({ to, label, Icon }) => <NavLink className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`} key={to} to={to}><Icon size={17} aria-hidden="true" />{label}</NavLink>)}</nav><div className={styles.sideFooter}><span className={styles.identity}>{role}</span><button className={styles.secondaryButton} type="button" onClick={logout}><LogOut size={15} aria-hidden="true" /> 登出</button></div></aside><main className={styles.main} id="main-content" tabIndex={-1}><header className={styles.topbar}><p className={styles.topbarTitle}>SouWen 管理面板</p><div className={styles.topbarActions}><button className={styles.iconButton} type="button" onClick={toggleTheme} aria-label={dark ? '切换为浅色模式' : '切换为深色模式'}>{dark ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}</button></div></header><div className={styles.content}><Outlet /></div></main></div></div>
}

function LoginPage() {
  const navigate = useNavigate(); const setAuth = useAuthStore((state) => state.setAuth); const setRole = useAuthStore((state) => state.setRole); const authenticated = useAuthStore((state) => state.isAuthenticated)
  const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem('souwen_baseUrl') ?? sessionStorage.getItem('souwen_baseUrl') ?? window.location.origin); const [token, setToken] = useState(''); const [remember, setRemember] = useState(false); const [state, setState] = useState<DataState<null>>({ status: 'idle' })
  useEffect(() => { if (authenticated) navigate('/search', { replace: true }) }, [authenticated, navigate])
  async function connect(event: FormEvent) { event.preventDefault(); setState({ status: 'loading' }); try { const url = baseUrl.replace(/\/+$/, ''); const health = await adminClient.health(url); const whoami = await adminClient.verifyAuth(url, token); setAuth(url, token, health.version, remember); setRole(whoami); setState({ status: 'success', data: null }); navigate('/search', { replace: true }) } catch (error) { setState({ status: 'error', error: formatError(error) }) } }
  return <div className={styles.login}><section className={`${styles.panel} ${styles.loginCard}`} aria-labelledby="login-title"><header className={styles.loginHeader}><p className={styles.eyebrow}>SouWen</p><h1 className={styles.loginTitle} id="login-title">连接服务器</h1><p className={styles.loginNote}>令牌只发送给同源、loopback 或明确允许的 API 地址，不会用于提权。无密码管理员访问仅在服务端开启 SOUWEN_ADMIN_OPEN=1 时可用。</p></header><Status state={state} name="连接" /><form className={`${styles.form} ${styles.loginForm}`} onSubmit={connect}><div className={styles.field}><label className={styles.label} htmlFor="server-url">Server URL</label><input className={styles.input} id="server-url" name="server-url" type="url" inputMode="url" autoComplete="url" required value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></div><div className={styles.field}><label className={styles.label} htmlFor="access-token">访问令牌</label><input className={styles.input} id="access-token" name="access-token" type="password" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="current-password" /><span className={styles.hint}>服务端未开放无密码访问时，输入对应角色的令牌。</span></div><label className={styles.choice}><input type="checkbox" name="remember" checked={remember} onChange={(event) => setRemember(event.target.checked)} />在此设备保留会话</label><button className={styles.button} type="submit" disabled={state.status === 'loading'} aria-busy={state.status === 'loading'}>连接</button></form></section></div>
}

function AuthGuard() { return useAuthStore((state) => state.isAuthenticated) ? <Shell /> : <Navigate to="/login" replace /> }
function AdminGuard({ children }: { children: ReactNode }) { return useAuthStore((state) => state.role) === 'admin' ? <>{children}</> : <Navigate to="/search" replace /> }

export function CalmPrecisionApp() {
  const load = useAuthStore((state) => state.loadFromStorage); const [ready, setReady] = useState(false)
  useEffect(() => { load(); if (useAuthStore.getState().isExpired()) useAuthStore.getState().logout(); document.documentElement.dataset.mode = localStorage.getItem('souwen_mode') === 'dark' ? 'dark' : 'light'; setReady(true) }, [load])
  if (!ready) return <div className={styles.login} role="status">正在恢复会话…</div>
  return <HashRouter><Routes><Route path="/login" element={<LoginPage />} /><Route element={<AuthGuard />}><Route path="/search" element={<SearchPage />} /><Route path="/llm-search" element={<LlmSearchPage />} /><Route path="/fetch" element={<FetchPage />} /><Route path="/providers" element={<ProvidersPage />} /><Route path="/runtime" element={<AdminGuard><AdminPage kind="runtime" /></AdminGuard>} /><Route path="/settings" element={<AdminGuard><AdminPage kind="settings" /></AdminGuard>} /><Route index element={<Navigate to="/search" replace />} /></Route><Route path="*" element={<Navigate to="/search" replace />} /></Routes></HashRouter>
}
