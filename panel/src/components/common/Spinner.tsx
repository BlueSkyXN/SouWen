interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export function Spinner({ size = 'md', label }: SpinnerProps) {
  const dim = size === 'sm' ? 20 : size === 'lg' ? 36 : 24
  const bw = size === 'lg' ? 3 : 2
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px',
        gap: '12px',
        color: 'var(--text-secondary)',
        fontSize: '13px',
      }}
    >
      <div
        style={{
          display: 'inline-block',
          width: dim,
          height: dim,
          border: `${bw}px solid var(--border)`,
          borderTopColor: 'var(--primary)',
          borderRadius: '50%',
          animation: 'spin 0.6s linear infinite',
        }}
      />
      {label && <span>{label}</span>}
    </div>
  )
}
