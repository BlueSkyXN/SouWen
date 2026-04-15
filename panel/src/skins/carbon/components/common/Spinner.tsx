interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export function Spinner({ size = 'md', label }: SpinnerProps) {
  const dim = size === 'sm' ? 16 : size === 'lg' ? 32 : 22

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px',
        gap: '12px',
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)',
        fontSize: '12px',
        letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}
    >
      <div
        style={{
          width: dim,
          height: dim,
          border: '2px solid var(--border)',
          borderTop: '2px solid var(--accent)',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      {label && <span>{label}</span>}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
