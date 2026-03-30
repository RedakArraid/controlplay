import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variants: Record<Variant, string> = {
  primary:
    'bg-gradient-to-r from-cp-accent to-cp-vr text-white font-semibold shadow-lg shadow-cp-accent/25 hover:brightness-110',
  secondary:
    'bg-cp-surface border border-cp-border text-cp-text hover:border-cp-accent/50',
  ghost: 'text-cp-muted hover:text-cp-text hover:bg-white/5',
  danger: 'bg-cp-danger/90 text-white hover:bg-cp-danger',
}

export function Button({
  className,
  variant = 'primary',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-cp-accent/60 disabled:opacity-40',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}
