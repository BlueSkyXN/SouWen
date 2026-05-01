/**
 * 文件用途：Souwen-Nebula 皮肤的插件管理页面
 *
 * 该页面是 PluginsPanel 的薄壳：负责标题/描述/容器布局，
 * 实际功能（列表、启用/禁用、健康检查、安装/卸载）由共享组件
 * @core/components/Plugins 提供，状态管理在 @core/hooks/usePluginsPage。
 */

import { useTranslation } from 'react-i18next'
import { m } from 'framer-motion'
import { Puzzle } from 'lucide-react'
import { staggerContainer, staggerItem } from '@core/lib/animations'
import { PluginsPanel } from '@core/components/Plugins'
import styles from './ConfigPage.module.scss'

export function PluginsPage() {
  const { t } = useTranslation()

  return (
    <m.div
      className={styles.page}
      variants={staggerContainer}
      initial="initial"
      animate="animate"
    >
      <m.div className={styles.pageHeader} variants={staggerItem}>
        <div>
          <h1 className={styles.pageTitle}>
            <Puzzle size={20} />
            {t('plugins.title')}
          </h1>
          <p className={styles.pageDesc}>{t('plugins.subtitle')}</p>
        </div>
      </m.div>

      <m.div variants={staggerItem}>
        <PluginsPanel />
      </m.div>
    </m.div>
  )
}
