import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import { apiGet, ApiError } from '../lib/api'
import type { AdminBootstrap, AuthMe } from '../types'

interface AuthContextValue {
  me: AuthMe | null
  boot: AdminBootstrap | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  clear: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<AuthMe | null>(null)
  const [boot, setBoot] = useState<AdminBootstrap | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const clear = useCallback(() => {
    setMe(null)
    setBoot(null)
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [u, b] = await Promise.all([
        apiGet<AuthMe>('/auth/me'),
        apiGet<AdminBootstrap>('/admin/bootstrap'),
      ])
      setMe(u)
      setBoot(b)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setMe(null)
        setBoot(null)
      } else {
        setError(e instanceof Error ? e.message : 'Erreur')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <AuthContext.Provider value={{ me, boot, loading, error, refresh, clear }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
