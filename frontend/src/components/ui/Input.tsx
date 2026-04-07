import { type InputHTMLAttributes, forwardRef } from 'react'
import { cn } from '../../lib/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helper?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helper, className, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="text-xs font-medium uppercase tracking-wider text-cp-muted"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'w-full rounded-xl border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition',
            'focus:outline-none focus:ring-2',
            error
              ? 'border-cp-danger/50 focus:border-cp-danger focus:ring-cp-danger/20'
              : 'border-cp-border focus:border-cp-cyan/50 focus:ring-cp-cyan/10',
            className,
          )}
          {...props}
        />
        {error && <p className="text-xs text-cp-danger">{error}</p>}
        {helper && !error && <p className="text-xs text-cp-muted">{helper}</p>}
      </div>
    )
  },
)
Input.displayName = 'Input'
