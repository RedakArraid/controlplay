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
    // Only fetch auth once on mount — not on every route change
    let cancelled = false
    ;(async () => {
      try {
        const [u, b] = await Promise.all([
          apiGet<AuthMe>('/auth/me'),
          apiGet<AdminBootstrap>('/admin/bootstrap'),
        ])
        if (cancelled) return
        setMe(u)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // No loc.pathname dependency — no reload on route change

  if (me === undefined && !err) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 rounded-full border-2 border-cp-cyan/30 border-t-cp-cyan animate-spin" />
          <p className="text-sm text-cp-muted">Chargement…</p>
        </div>
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
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-cp-danger">{err ?? 'Navigation indisponible'}</p>
        <button
          onClick={() => window.location.reload()}
          className="rounded-xl border border-white/10 px-4 py-2 text-sm text-cp-muted hover:bg-white/5"
        >
          Réessayer
        </button>
      </div>
    )
  }

  if (!me || !boot) return null;

  return (
    <AppShell zone="admin" title="Administration" nav={boot.nav} userLabel={me.user.name}>
      <Outlet context={{ me, boot }} />
    </AppShell>
  )
}
