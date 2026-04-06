import { Loader2 } from 'lucide-react'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

export function Spinner({ size = 'md', label }: SpinnerProps) {
  const dim = size === 'sm' ? 20 : size === 'lg' ? 36 : 24
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
      <Loader2
        size={dim}
        style={{ animation: 'spin 0.6s linear infinite' }}
        color="var(--primary)"
      />
      {label && <span>{label}</span>}
    </div>
  )
}
