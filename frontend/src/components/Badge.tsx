import type { HTMLAttributes } from 'react'
import { cn } from '../lib/cn'

type Tone = 'default' | 'ok' | 'warn' | 'bad' | 'muted'

const tones: Record<Tone, string> = {
  default: 'bg-cp-accent/15 text-cp-accent border-cp-accent/30',
  ok: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  warn: 'bg-amber-500/15 text-amber-200 border-amber-500/30',
  bad: 'bg-rose-500/15 text-rose-200 border-rose-500/30',
  muted: 'bg-white/5 text-cp-muted border-cp-border',
}

export function Badge({
  className,
  tone = 'default',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-lg border px-2 py-0.5 text-xs font-medium',
        tones[tone],
        className,
      )}
      {...props}
    />
  )
}
