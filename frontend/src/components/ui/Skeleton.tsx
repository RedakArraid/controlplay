import { cn } from '../../lib/cn'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'skeleton-shimmer rounded-xl',
        className,
      )}
    />
  )
}

export function SkeletonCard() {
  return (
    <div className="glass-panel rounded-2xl border border-white/5 p-6">
      <Skeleton className="mb-3 h-4 w-1/3" />
      <Skeleton className="mb-2 h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
      <div className="border-b border-white/5 px-4 py-3">
        <Skeleton className="h-3 w-32" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 border-b border-white/5 px-4 py-3">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton
              key={j}
              className={cn('h-3', j === 0 ? 'w-24' : j === cols - 1 ? 'w-16' : 'flex-1')}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonKPI() {
  return (
    <div className="glass-panel rounded-2xl border border-white/5 p-5">
      <Skeleton className="mb-4 h-3 w-20" />
      <Skeleton className="mb-2 h-8 w-24" />
      <Skeleton className="h-3 w-32" />
    </div>
  )
}
