import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
}

interface ToastContextValue {
  toasts: Toast[]
  toast: (type: ToastType, title: string, message?: string) => void
  success: (title: string, message?: string) => void
  error: (title: string, message?: string) => void
  info: (title: string, message?: string) => void
  dismiss: (id: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (type: ToastType, title: string, message?: string) => {
      const id = Math.random().toString(36).slice(2)
      setToasts((prev) => [...prev, { id, type, title, message }])
      setTimeout(() => dismiss(id), 4500)
    },
    [dismiss],
  )

  const success = useCallback(
    (title: string, message?: string) => toast('success', title, message),
    [toast],
  )
  const error = useCallback(
    (title: string, message?: string) => toast('error', title, message),
    [toast],
  )
  const info = useCallback(
    (title: string, message?: string) => toast('info', title, message),
    [toast],
  )

  const icons = { success: CheckCircle, error: XCircle, info: Info }
  const colors = {
    success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
    error: 'border-red-500/40 bg-red-500/10 text-red-300',
    info: 'border-cp-cyan/40 bg-cp-cyan/10 text-cp-cyan',
  }

  return (
    <ToastContext.Provider value={{ toasts, toast, success, error, info, dismiss }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[9999] flex w-80 flex-col gap-2">
        {toasts.map((t) => {
          const Icon = icons[t.type]
          return (
            <div
              key={t.id}
              className={`toast-enter glass-panel flex items-start gap-3 rounded-2xl border p-4 shadow-xl ${colors[t.type]}`}
            >
              <Icon className="mt-0.5 h-5 w-5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-cp-text">{t.title}</p>
                {t.message && <p className="mt-0.5 text-xs opacity-80">{t.message}</p>}
              </div>
              <button
                onClick={() => dismiss(t.id)}
                className="shrink-0 rounded-lg p-0.5 opacity-60 transition-opacity hover:opacity-100"
              >
                <X className="h-4 w-4 text-cp-muted" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
