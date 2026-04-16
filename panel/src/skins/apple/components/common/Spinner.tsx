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
        gap: '14px',
        fontFamily: 'var(--font-body)',
        color: 'var(--text-muted)',
        fontSize: '14px',
        letterSpacing: '-0.01em',
      }}
    >
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
      {label && <span>{label}</span>}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}
