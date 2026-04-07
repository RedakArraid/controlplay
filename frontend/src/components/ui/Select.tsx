import { type SelectHTMLAttributes, forwardRef, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  children: ReactNode
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, className, children, id, ...props }, ref) => {
    const selectId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={selectId}
            className="text-xs font-medium uppercase tracking-wider text-cp-muted"
          >
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={cn(
            'w-full rounded-xl border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text transition',
            'focus:outline-none focus:ring-2',
            error
              ? 'border-cp-danger/50 focus:ring-cp-danger/20'
              : 'border-cp-border focus:border-cp-cyan/50 focus:ring-cp-cyan/10',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        {error && <p className="text-xs text-cp-danger">{error}</p>}
      </div>
    )
  },
)
Select.displayName = 'Select'
