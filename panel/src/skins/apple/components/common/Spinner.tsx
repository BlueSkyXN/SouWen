/**
 * 文件用途：Apple 皮肤的加载旋转圈组件，用于异步操作等待状态的视觉反馈
 *
 * 组件/函数清单：
 *   Spinner（函数组件）
 *     - 功能：渲染一个可配置大小的旋转加载指示器，支持显示加载文本
 *     - Props 属性：size ('sm' | 'md' | 'lg') 旋转圈大小 (默认 'md'), label (string) 可选的加载文本标签
 *     - 输出：包含旋转动画的 React 元素
 *     - 关键变量：dim (number) 根据 size 计算的旋转圈直径（sm=16, md=22, lg=32）
 *     - 关键动画：spin 0.7s 线性无限循环旋转，360 度转圈
 *
 * 模块依赖：无外部依赖，仅依赖原生 React 和 CSS
 */

/**
 * Spinner 组件的 Props 接口
 * @property {('sm' | 'md' | 'lg')} [size='md'] - 旋转圈的大小尺寸
 * @property {string} [label] - 加载中显示的文本标签
 */
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

/**
 * Spinner 组件 - 加载等待指示器
 * 根据 size 属性动态计算旋转圈的宽高，支持显示加载文本
 * @param {SpinnerProps} props - 组件配置属性
 * @returns {JSX.Element} 旋转加载指示器 UI
 */
export function Spinner({ size = 'md', label }: SpinnerProps) {
  // 根据 size 计算旋转圈的直径像素值
  const dim = size === 'sm' ? 16 : size === 'lg' ? 32 : 22

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px',
        gap: '14px',
        fontFamily: 'var(--font-body)',
        color: 'var(--text-muted)',
        fontSize: '14px',
        letterSpacing: '-0.01em',
      }}
    >
      {/* 旋转圈 - 使用 border 绘制，上边框使用主题强调色 */}
      <div
        style={{
          width: dim,
          height: dim,
          border: '2px solid var(--border-strong)',
          borderTop: '2px solid var(--accent)',
          borderRadius: '50%',
          animation: 'spin 0.7s linear infinite',
        }}
      />
      {/* 可选的加载文本标签 */}
      {label && <span>{label}</span>}
      {/* 内联 CSS 定义 spin 动画 */}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
