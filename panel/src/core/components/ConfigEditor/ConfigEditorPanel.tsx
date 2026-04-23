/**
 * 文件用途：在线配置文件编辑器面板 —— 源文件编辑（CodeMirror YAML）+ 可视化模块编辑（表单）
 *
 * 组件：ConfigEditorPanel
 *   - Tab 1: YAML 源文件编辑器（@uiw/react-codemirror + @codemirror/lang-yaml）
 *   - Tab 2: 可视化模块编辑器（分节表单，自动解析 YAML 并回写）
 *
 * 公共 Props: className?: string
 */

import { useState, useCallback, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { EditorView } from '@codemirror/view'
import { oneDark } from '@codemirror/theme-one-dark'
import * as jsyaml from 'js-yaml'
import {
  Code2,
  LayoutDashboard,
  Save,
  ChevronDown,
  Eye,
  EyeOff,
  AlertTriangle,
} from 'lucide-react'
import { api } from '@core/services/api'
import { useNotificationStore } from '@core/stores/notificationStore'
import { formatError } from '@core/lib/errors'
import { YAML_SECTIONS } from './schema'
import type { FieldDef } from './schema'
import styles from './ConfigEditorPanel.module.scss'

/* ── helpers ─────────────────────────────── */

function parseYamlToFlat(content: string): Record<string, Record<string, unknown>> {
  try {
    const parsed = jsyaml.load(content)
    if (parsed && typeof parsed === 'object') {
      return parsed as Record<string, Record<string, unknown>>
    }
  } catch {
    // ignore parse errors — return empty object
  }
  return {}
}

function flatToYaml(sections: Record<string, Record<string, unknown>>, originalYaml?: string): string {
  // Preserve unknown top-level keys and fields from original YAML
  let baseObj: Record<string, Record<string, unknown>> = {}
  if (originalYaml) {
    try {
      baseObj = parseYamlToFlat(originalYaml)
    } catch {
      // If parsing fails, start with empty object
    }
  }

  // Merge visual values into base object, preserving unknown keys
  const merged: Record<string, Record<string, unknown>> = { ...baseObj }
  for (const [sec, fields] of Object.entries(sections)) {
    const cleanedFields: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(fields)) {
      if (v !== '' && v !== undefined) {
        cleanedFields[k] = v
      } else {
        cleanedFields[k] = null
      }
    }
    merged[sec] = { ...(baseObj[sec] ?? {}), ...cleanedFields }
  }

  return jsyaml.dump(merged, { indent: 2, lineWidth: 120, noRefs: true })
}

/* ── VisualField ─────────────────────────── */

interface VisualFieldProps {
  field: FieldDef
  value: unknown
  onChange: (key: string, value: unknown) => void
}

function VisualField({ field, value, onChange }: VisualFieldProps) {
  const [showPassword, setShowPassword] = useState(false)
  const { t } = useTranslation()

  if (field.type === 'boolean') {
    const checked = value === true || value === 'true'
    return (
      <div className={styles.fieldRow}>
        <label className={styles.fieldLabel}>{field.label}</label>
        <div className={styles.fieldInputWrapper}>
          <label className={styles.fieldToggle}>
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => onChange(field.key, e.target.checked)}
            />
            <span className={styles.toggleTrack} />
          </label>
        </div>
      </div>
    )
  }

  if (field.type === 'number') {
    const num = value !== null && value !== undefined && value !== '' ? Number(value) : ''
    return (
      <div className={styles.fieldRow}>
        <label className={styles.fieldLabel}>{field.label}</label>
        <div className={styles.fieldInputWrapper}>
          <input
            type="number"
            className={styles.fieldInput}
            value={num}
            placeholder={field.placeholder ?? t('config.fieldOptional')}
            onChange={(e) =>
              onChange(field.key, e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </div>
      </div>
    )
  }

  if (field.type === 'password') {
    const strVal = value !== null && value !== undefined ? String(value) : ''
    return (
      <div className={styles.fieldRow}>
        <label className={styles.fieldLabel}>{field.label}</label>
        <div className={styles.fieldInputWrapper}>
          <input
            type={showPassword ? 'text' : 'password'}
            className={styles.fieldInput}
            value={strVal}
            placeholder={field.placeholder ?? t('config.fieldOptional')}
            autoComplete="off"
            onChange={(e) => onChange(field.key, e.target.value || null)}
          />
          <button
            type="button"
            className={styles.eyeBtn}
            onClick={() => setShowPassword((p) => !p)}
            title={showPassword ? '隐藏' : '显示'}
          >
            {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
      </div>
    )
  }

  // text, url, email
  const strVal = value !== null && value !== undefined ? String(value) : ''
  return (
    <div className={styles.fieldRow}>
      <label className={styles.fieldLabel}>{field.label}</label>
      <div className={styles.fieldInputWrapper}>
        <input
          type={field.type === 'email' ? 'email' : field.type === 'url' ? 'url' : 'text'}
          className={styles.fieldInput}
          value={strVal}
          placeholder={field.placeholder ?? t('config.fieldOptional')}
          onChange={(e) => onChange(field.key, e.target.value || null)}
        />
      </div>
    </div>
  )
}

/* ── VisualSection ───────────────────────── */

interface VisualSectionProps {
  sectionKey: string
  titleI18nKey: string
  fields: FieldDef[]
  values: Record<string, unknown>
  onFieldChange: (sectionKey: string, fieldKey: string, value: unknown) => void
  defaultOpen?: boolean
}

function VisualSection({
  sectionKey,
  titleI18nKey,
  fields,
  values,
  onFieldChange,
  defaultOpen = false,
}: VisualSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const { t } = useTranslation()

  return (
    <div className={styles.visualSection}>
      <div className={styles.sectionHeader} onClick={() => setOpen((o) => !o)}>
        <span className={styles.sectionTitle}>{t(titleI18nKey)}</span>
        <ChevronDown
          size={16}
          className={`${styles.sectionChevron} ${open ? styles.open : ''}`}
        />
      </div>
      {open && (
        <div className={styles.sectionBody}>
          {fields.map((field) => (
            <VisualField
              key={field.key}
              field={field}
              value={values[field.key] ?? null}
              onChange={(key, val) => onFieldChange(sectionKey, key, val)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/* ── ConfigEditorPanel ───────────────────── */

type TabId = 'source' | 'visual'

interface Props {
  className?: string
}

export function ConfigEditorPanel({ className }: Props) {
  const { t } = useTranslation()
  const addToast = useNotificationStore((s) => s.addToast)

  const [activeTab, setActiveTab] = useState<TabId>('source')
  const [yamlContent, setYamlContent] = useState('')
  const [configPath, setConfigPath] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Visual editor state: sectionKey -> fieldKey -> value
  const [visualValues, setVisualValues] = useState<Record<string, Record<string, unknown>>>({})
  const [visualDirty, setVisualDirty] = useState(false)
  // Track original yaml for source editor dirty detection
  const [originalYaml, setOriginalYaml] = useState('')

  // Detect dark theme by checking document theme attribute or CSS variables
  const [isDarkTheme, setIsDarkTheme] = useState(() => {
    if (typeof document === 'undefined') return false
    const htmlEl = document.documentElement
    // Check data-theme or class attribute for theme detection
    return (
      htmlEl.dataset.theme === 'dark' ||
      htmlEl.dataset.mode === 'dark' ||
      htmlEl.className.includes('dark') ||
      window.matchMedia('(prefers-color-scheme: dark)').matches
    )
  })

  // Monitor theme changes
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const htmlEl = document.documentElement
      const dark =
        htmlEl.dataset.theme === 'dark' ||
        htmlEl.dataset.mode === 'dark' ||
        htmlEl.className.includes('dark') ||
        window.matchMedia('(prefers-color-scheme: dark)').matches
      setIsDarkTheme(dark)
    })

    observer.observe(document.documentElement, { attributes: true })

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (e: MediaQueryListEvent) => setIsDarkTheme(e.matches)
    mediaQuery.addEventListener('change', handleChange)

    return () => {
      observer.disconnect()
      mediaQuery.removeEventListener('change', handleChange)
    }
  }, [])

  const codemirrorTheme = useMemo(() => (isDarkTheme ? oneDark : undefined), [isDarkTheme])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.getConfigYaml()
      setYamlContent(res.content)
      setOriginalYaml(res.content)
      setConfigPath(res.path)
      // Initialize visual editor from parsed YAML
      const parsed = parseYamlToFlat(res.content)
      setVisualValues(parsed)
      setVisualDirty(false)
    } catch (err) {
      addToast('error', t('config.yamlFetchFailed', { message: formatError(err) }))
    } finally {
      setLoading(false)
    }
  }, [addToast, t])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  // Sync: when switching from visual to source, regenerate YAML from visual state
  const handleTabChange = useCallback(
    (tab: TabId) => {
      if (activeTab === 'visual' && tab === 'source' && visualDirty) {
        const newYaml = flatToYaml(visualValues, yamlContent)
        setYamlContent(newYaml)
      } else if (activeTab === 'source' && tab === 'visual') {
        // Validate YAML syntax before switching
        try {
          jsyaml.load(yamlContent)
        } catch (err) {
          addToast('error', t('config.yamlSyntaxError', { message: String(err) }))
          return // Prevent tab switch on validation error
        }
        // Re-parse source YAML into visual state
        const parsed = parseYamlToFlat(yamlContent)
        setVisualValues(parsed)
        setVisualDirty(false)
      }
      setActiveTab(tab)
    },
    [activeTab, visualDirty, visualValues, yamlContent, originalYaml, addToast, t],
  )

  const handleVisualFieldChange = useCallback(
    (sectionKey: string, fieldKey: string, value: unknown) => {
      setVisualValues((prev) => ({
        ...prev,
        [sectionKey]: {
          ...(prev[sectionKey] ?? {}),
          [fieldKey]: value,
        },
      }))
      setVisualDirty(true)
    },
    [],
  )

  const handleSaveSource = useCallback(async () => {
    setSaving(true)
    try {
      const res = await api.saveConfigYaml(yamlContent)
      setOriginalYaml(yamlContent)
      setConfigPath(res.path)
      addToast('success', t('config.saveYamlSuccess'))
      // Refresh visual values
      const parsed = parseYamlToFlat(yamlContent)
      setVisualValues(parsed)
      setVisualDirty(false)
    } catch (err) {
      addToast('error', t('config.saveYamlFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [addToast, t, yamlContent])

  const handleSaveVisual = useCallback(async () => {
    setSaving(true)
    try {
      const newYaml = flatToYaml(visualValues, originalYaml)
      const res = await api.saveConfigYaml(newYaml)
      setYamlContent(newYaml)
      setOriginalYaml(newYaml)
      setConfigPath(res.path)
      setVisualDirty(false)
      addToast('success', t('config.saveYamlSuccess'))
    } catch (err) {
      addToast('error', t('config.saveYamlFailed', { message: formatError(err) }))
    } finally {
      setSaving(false)
    }
  }, [addToast, t, visualValues, originalYaml])

  const sourceDirty = yamlContent !== originalYaml

  if (loading) {
    return <div className={styles.panel} />
  }

  return (
    <div className={`${styles.panel} ${className ?? ''}`}>
      {/* ── Tab Bar ── */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'source' ? styles.active : ''}`}
          onClick={() => handleTabChange('source')}
        >
          <Code2 size={14} />
          {t('config.editorTabSource')}
          {sourceDirty && activeTab !== 'source' && <AlertTriangle size={12} />}
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'visual' ? styles.active : ''}`}
          onClick={() => handleTabChange('visual')}
        >
          <LayoutDashboard size={14} />
          {t('config.editorTabVisual')}
          {visualDirty && activeTab !== 'visual' && <AlertTriangle size={12} />}
        </button>
      </div>

      {/* ── Source Editor Tab ── */}
      {activeTab === 'source' && (
        <div className={styles.tabContent}>
          <div className={styles.yamlEditorWrapper}>
            <div className={styles.editorContainer}>
              <CodeMirror
                value={yamlContent}
                onChange={setYamlContent}
                extensions={[yaml(), EditorView.lineWrapping]}
                theme={codemirrorTheme}
                basicSetup={{
                  lineNumbers: true,
                  foldGutter: true,
                  highlightActiveLine: true,
                  bracketMatching: true,
                  autocompletion: true,
                }}
                height="100%"
              />
            </div>
            <div className={styles.editorActions}>
              <div className={styles.pathHint}>
                {configPath ? (
                  <>
                    {t('config.configFilePath')}: <span>{configPath}</span>
                  </>
                ) : (
                  <span>{t('config.noConfigFile')}</span>
                )}
              </div>
              <button
                className={styles.saveBtn}
                onClick={() => void handleSaveSource()}
                disabled={saving || !sourceDirty}
              >
                <Save size={14} />
                {saving ? t('config.savingYaml') : t('config.saveYaml')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Visual Editor Tab ── */}
      {activeTab === 'visual' && (
        <div className={styles.tabContent}>
          <div className={styles.visualEditor}>
            {YAML_SECTIONS.map((section) => (
              <VisualSection
                key={section.key}
                sectionKey={section.key}
                titleI18nKey={section.titleI18nKey}
                fields={section.fields}
                values={visualValues[section.key] ?? {}}
                onFieldChange={handleVisualFieldChange}
                defaultOpen={section.key === 'server' || section.key === 'general'}
              />
            ))}
            {/* Sources section — raw YAML editor notice */}
            <div className={styles.visualSection}>
              <div className={styles.sectionHeader}>
                <span className={styles.sectionTitle}>{t('config.visualSectionSources')}</span>
              </div>
              <div className={styles.sectionBody}>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary, #888)', margin: 0 }}>
                  {t('config.visualSectionSourcesHint')}
                </p>
              </div>
            </div>
          </div>
          <div className={styles.editorActions}>
            {visualDirty && (
              <span className={styles.unsavedBadge}>
                <AlertTriangle size={12} />
                {t('config.unsavedChanges')}
              </span>
            )}
            <button
              className={styles.saveBtn}
              onClick={() => void handleSaveVisual()}
              disabled={saving || !visualDirty}
            >
              <Save size={14} />
              {saving ? t('config.savingYaml') : t('config.saveYaml')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
