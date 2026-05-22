import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AppShell } from '../components/Shell'
import { ApiError, apiGet } from '../lib/api'
import type { AdminBootstrap, AuthMe } from '../types'

export function SuperAdminLayout() {
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
        const zoneOk =
          u.is_super_admin ||
          (u.is_platform_staff && (u.staff_permissions?.length ?? 0) > 0)
        if (!zoneOk) {
          setMe(u)
          setBoot(null)
          setErr('Accès réservé (super administrateur ou équipe ControlPlay autorisée)')
          return
        }
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
    // Intentionnellement sans dépendance à loc : même logique que AdminLayout (pas de reload à chaque route).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  if (me === undefined) {
    return (
      <div className="flex min-h-screen items-center justify-center text-cp-muted">
        Chargement…
      </div>
    )
  }

  const superZoneOk =
    me.is_super_admin ||
    (me.is_platform_staff && (me.staff_permissions?.length ?? 0) > 0)
  if (!superZoneOk) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <p className="max-w-md text-cp-muted">{err}</p>
        <a href="/admin" className="text-cp-teal hover:underline">
          Retour administration
        </a>
      </div>
    )
  }

  if (err || !boot) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-rose-300">{err ?? 'Erreur'}</p>
      </div>
    )
  }

  return (
    <AppShell
      zone="super"
      title="Super administrateur"
      nav={boot.nav}
      userLabel={me.user.name}
    >
      <Outlet context={{ me, boot } as { me: AuthMe; boot: AdminBootstrap | null }} />
    </AppShell>
  )
}
