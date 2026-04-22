/**
 * 骨架屏加载组件 - 占位符加载动画
 *
 * 文件用途：提供多种预定义的骨架屏变体，用于数据加载前的占位显示
 *
 * 函数/类清单：
 *   Skeleton（React.FC<SkeletonProps>）
 *     - 功能：单个骨架屏元素，支持多种变体和自定义尺寸
 *     - Props:
 *       - width (number | string, 可选): 宽度
 *       - height (number | string, 可选): 高度
 *       - variant (string, 默认 'rect'): 骨架屏变体
 *         - 'text': 单行文本
 *         - 'textShort': 短文本
 *         - 'textLong': 长段落
 *         - 'title': 标题
 *         - 'circle': 圆形头像
 *         - 'rect': 矩形
 *       - className (string, 可选): 自定义 CSS 类
 *       - style (CSSProperties, 可选): 内联样式
 *
 *   StatCardSkeleton / StatsGridSkeleton（React.FC）
 *     - 功能：预配置的统计卡片加载骨架
 *
 *   TableRowSkeleton / TableSkeleton（React.FC）
 *     - 功能：预配置的表格加载骨架，支持行列数自定义
 *
 *   ResultCardSkeleton / ResultsSkeleton（React.FC）
 *     - 功能：预配置的搜索结果卡片加载骨架
 */

import React from 'react';
import styles from './Skeleton.module.scss';

interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  variant?: 'text' | 'textShort' | 'textLong' | 'title' | 'circle' | 'rect';
  className?: string;
  style?: React.CSSProperties;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width,
  height,
  variant = 'rect',
  className = '',
  style,
}) => (
  // 骨架屏元素 - 通过 CSS 动画提供加载效果
  <div
    className={`${styles.skeleton} ${styles[variant]} ${className}`}
    style={{ width, height, ...style }}
  />
);

/* ===== 复合骨架屏（预配置组合） ===== */

export const StatCardSkeleton: React.FC = () => (
  <div className={styles.statCardSkeleton}>
    <div className={styles.statCardHeader}>
      <Skeleton variant="textShort" width="60%" />
      <Skeleton variant="rect" width={36} height={36} />
    </div>
    <Skeleton variant="title" width="45%" height={28} />
  </div>
);

export const StatsGridSkeleton: React.FC<{ count?: number }> = ({ count = 5 }) => (
  <div className={styles.statsGridSkeleton}>
    {Array.from({ length: count }, (_, i) => (
      <StatCardSkeleton key={i} />
    ))}
  </div>
);

export const TableRowSkeleton: React.FC = () => (
  <div className={styles.tableRowSkeleton}>
    <Skeleton variant="text" width="20%" />
    <Skeleton variant="text" width="12%" />
    <Skeleton variant="text" width="10%" />
    <Skeleton variant="textShort" width="25%" />
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number; cols?: number }> = ({
  rows = 5,
  cols = 4,
}) => (
  <div className={styles.tableWrapSkeleton}>
    <div className={styles.tableHeaderSkeleton}>
      {Array.from({ length: cols }, (_, i) => (
        <Skeleton key={i} variant="textShort" width={`${60 + i * 10}px`} height={12} />
      ))}
    </div>
    {Array.from({ length: rows }, (_, i) => (
      <TableRowSkeleton key={i} />
    ))}
  </div>
);

// 搜索结果卡片骨架
export const ResultCardSkeleton: React.FC = () => (
  <div className={styles.resultCardSkeleton}>
    <Skeleton variant="title" width="70%" />
    <Skeleton variant="text" width="40%" />
    <Skeleton variant="textLong" />
    <Skeleton variant="text" width="90%" />
  </div>
);

// 搜索结果列表骨架
export const ResultsSkeleton: React.FC<{ count?: number }> = ({ count = 3 }) => (
  <div>
    {Array.from({ length: count }, (_, i) => (
      <ResultCardSkeleton key={i} />
    ))}
  </div>
);
