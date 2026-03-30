import type { HTMLAttributes } from 'react'
import { cn } from '../lib/cn'

export function Card({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('glass-panel rounded-2xl p-6', className)}
      {...props}
    />
  )
}

export function CardTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        'text-lg font-semibold tracking-tight text-cp-text',
        className,
      )}
      {...props}
    />
  )
}
