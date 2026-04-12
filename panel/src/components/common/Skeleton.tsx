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
  <div
    className={`${styles.skeleton} ${styles[variant]} ${className}`}
    style={{ width, height, ...style }}
  />
);

/* ===== Composite Skeletons ===== */

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

export const ResultCardSkeleton: React.FC = () => (
  <div className={styles.resultCardSkeleton}>
    <Skeleton variant="title" width="70%" />
    <Skeleton variant="text" width="40%" />
    <Skeleton variant="textLong" />
    <Skeleton variant="text" width="90%" />
  </div>
);

export const ResultsSkeleton: React.FC<{ count?: number }> = ({ count = 3 }) => (
  <div>
    {Array.from({ length: count }, (_, i) => (
      <ResultCardSkeleton key={i} />
    ))}
  </div>
);
