import React from 'react';
import styles from './EmptyState.module.scss';

type IllustrationType = 'search' | 'noData' | 'error';

interface EmptyStateProps {
  type?: IllustrationType;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

const SearchIllustration = () => (
  <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className={styles.illustration}>
    <circle cx="52" cy="52" r="30" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <line x1="74" y1="74" x2="98" y2="98" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <line x1="40" y1="52" x2="64" y2="52" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.4" />
    <line x1="52" y1="40" x2="52" y2="64" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.4" />
  </svg>
);

const NoDataIllustration = () => (
  <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className={styles.illustration}>
    <rect x="25" y="35" width="70" height="55" rx="4" stroke="currentColor" strokeWidth="3" />
    <line x1="25" y1="50" x2="95" y2="50" stroke="currentColor" strokeWidth="2" opacity="0.3" />
    <line x1="40" y1="62" x2="80" y2="62" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
    <line x1="40" y1="72" x2="70" y2="72" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.3" />
    <path d="M52 25 L60 18 L68 25" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.5" />
    <line x1="60" y1="18" x2="60" y2="35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
  </svg>
);

const ErrorIllustration = () => (
  <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className={styles.illustration}>
    <circle cx="60" cy="60" r="35" stroke="currentColor" strokeWidth="3" />
    <line x1="60" y1="40" x2="60" y2="68" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    <circle cx="60" cy="80" r="3" fill="currentColor" />
  </svg>
);

const illustrations: Record<IllustrationType, React.FC> = {
  search: SearchIllustration,
  noData: NoDataIllustration,
  error: ErrorIllustration,
};

export const EmptyState: React.FC<EmptyStateProps> = ({
  type = 'noData',
  title,
  description,
  action,
}) => {
  const Illustration = illustrations[type];
  return (
    <div className={styles.emptyState}>
      <Illustration />
      <div className={styles.title}>{title}</div>
      {description && <div className={styles.description}>{description}</div>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
};
