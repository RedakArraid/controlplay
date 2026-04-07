import { cn } from '../lib/cn'

type Tone = 'ok' | 'warn' | 'bad' | 'muted' | 'info' | 'default'

const toneClasses: Record<Tone, string> = {
  ok: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  warn: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  bad: 'bg-red-500/15 text-red-300 border-red-500/30',
  muted: 'bg-white/5 text-cp-muted border-white/10',
  info: 'bg-cp-cyan/10 text-cp-cyan border-cp-cyan/30',
  default: 'bg-cp-accent/10 text-cp-accent border-cp-accent/30',
}

export function Badge({
  tone = 'muted',
  children,
  className,
}: {
  tone?: Tone
  children: React.ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
