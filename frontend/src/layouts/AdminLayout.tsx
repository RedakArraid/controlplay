import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AppShell } from '../components/Shell'
import { ApiError, apiGet } from '../lib/api'
import type { AdminBootstrap, AuthMe } from '../types'

export function AdminLayout() {
  const loc = useLocation()
  const [me, setMe] = useState<AuthMe | null | undefined>(undefined)
  const [boot, setBoot] = useState<AdminBootstrap | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const u = await apiGet<AuthMe>('/auth/me')
        if (cancelled) return
        setMe(u)
        const b = await apiGet<AdminBootstrap>('/admin/bootstrap')
        if (cancelled) return
        setBoot(b)
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 401) {
          setMe(null)
          return
        }
        setErr(e instanceof Error ? e.message : 'Erreur')
        setMe(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loc.pathname])

  if (me === undefined && !err) {
    return (
      <div className="flex min-h-screen items-center justify-center text-cp-muted">
        Chargement…
      </div>
    )
  }

  if (me === null) {
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`}
        replace
      />
    )
  }

  if (err || !boot) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-rose-300">{err ?? 'Navigation indisponible'}</p>
      </div>
    )
  }

  if (!me) {
    return (
      <div className="flex min-h-screen items-center justify-center text-cp-muted">
        Chargement…
      </div>
    )
  }

  return (
    <AppShell
      zone="admin"
      title="Administration"
      nav={boot.nav}
      userLabel={me.user.name}
    >
      <Outlet context={{ me, boot }} />
    </AppShell>
  )
}
