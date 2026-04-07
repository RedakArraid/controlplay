import { useEffect, useRef, useState } from 'react'
import { Badge } from '../../components/Badge'
import { SkeletonKPI, SkeletonTable } from '../../components/ui/Skeleton'
import { apiGet } from '../../lib/api'
import {
  Activity,
  CheckCircle2,
  Clock,
  Gamepad2,
  RefreshCw,
  TrendingUp,
  Wifi,
  WifiOff,
  Zap,
} from 'lucide-react'

type Row = {
  code: string
  name: string
  state: string
  remaining_s: string
  duration_min: number | null
  price_xof: number | null
  provider: string
}

type Summary = {
  paystack: boolean
  cinetpay: boolean
  stations: Row[]
  empty: boolean
}

function stateTone(s: string): 'ok' | 'warn' | 'bad' | 'muted' | 'info' {
  if (s === 'OK') return 'ok'
  if (s === 'ACTIVE') return 'info'
  if (s === 'PENDING') return 'muted'
  if (s === 'PAUSE') return 'warn'
  return 'bad'
}

function stateLabel(s: string) {
  if (s === 'OK') return 'Libre'
  if (s === 'ACTIVE') return 'En jeu'
  if (s === 'PENDING') return 'En attente'
  if (s === 'PAUSE') return 'Pause'
  return s
}

function StatusDot({ state }: { state: string }) {
  const cls =
    state === 'ACTIVE'
      ? 'active'
      : state === 'PAUSE'
        ? 'paused'
        : state === 'PENDING'
          ? 'pending'
          : 'idle'
  return <span className={`status-dot ${cls}`} />
}

function formatTimer(remaining: string) {
  if (!remaining) return '—'
  const s = parseInt(remaining)
  if (isNaN(s)) return remaining
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export function AdminDashboard({
  title = 'Tableau de bord',
  description = 'Vue temps réel des stations actives dans votre périmètre.',
}: {
  title?: string
  description?: string
}) {
  const [data, setData] = useState<Summary | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const d = await apiGet<Summary>('/admin/dashboard/summary')
      setData(d)
      setLastUpdated(new Date())
      setErr(null)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchData()
    intervalRef.current = setInterval(() => fetchData(true), 30_000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  // KPI derivations
  const activeCount = data?.stations.filter((s) => s.state === 'ACTIVE').length ?? 0
  const pausedCount = data?.stations.filter((s) => s.state === 'PAUSE').length ?? 0
  const totalCount = data?.stations.length ?? 0
  const revenueToday = data?.stations.reduce((sum, s) => {
    return s.state === 'ACTIVE' && s.price_xof ? sum + s.price_xof : sum
  }, 0) ?? 0

  return (
    <div className="animate-fadeIn">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">{title}</h1>
          <p className="mt-1 text-sm text-cp-muted">{description}</p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-cp-muted">
              Mis à jour {lastUpdated.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          )}
          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-text disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Rafraîchir
          </button>
        </div>
      </div>

      {/* PSP status */}
      {data && (
        <div className="mb-6 flex flex-wrap gap-2">
          <div
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
              data.paystack
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-white/10 bg-white/5 text-cp-muted'
            }`}
          >
            {data.paystack ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            Paystack {data.paystack ? 'actif' : 'inactif'}
          </div>
          <div
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
              data.cinetpay
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                : 'border-white/10 bg-white/5 text-cp-muted'
            }`}
          >
            {data.cinetpay ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
            CinetPay {data.cinetpay ? 'actif' : 'inactif'}
          </div>
        </div>
      )}

      {err && (
        <div className="mb-6 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {err}
        </div>
      )}

      {/* KPI Cards */}
      {loading ? (
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => <SkeletonKPI key={i} />)}
        </div>
      ) : (
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="kpi-card glass-panel rounded-2xl border border-white/5 p-5 animate-fadeIn stagger-1">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-cp-muted">Stations totales</p>
              <Gamepad2 className="h-4 w-4 text-cp-muted" />
            </div>
            <p className="mt-3 font-display text-3xl font-bold animate-countUp">{totalCount}</p>
            <p className="mt-1 text-xs text-cp-muted">dans votre périmètre</p>
          </div>

          <div className="kpi-card glass-panel rounded-2xl border border-cp-cyan/20 p-5 animate-fadeIn stagger-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-cp-muted">En jeu</p>
              <Activity className="h-4 w-4 text-cp-cyan animate-pulseGlow" />
            </div>
            <p className="mt-3 font-display text-3xl font-bold text-cp-cyan animate-countUp">{activeCount}</p>
            <p className="mt-1 text-xs text-cp-muted">sessions actives</p>
          </div>

          <div className="kpi-card glass-panel rounded-2xl border border-amber-500/20 p-5 animate-fadeIn stagger-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-cp-muted">En pause</p>
              <Clock className="h-4 w-4 text-amber-400" />
            </div>
            <p className="mt-3 font-display text-3xl font-bold text-amber-400 animate-countUp">{pausedCount}</p>
            <p className="mt-1 text-xs text-cp-muted">stations en pause</p>
          </div>

          <div className="kpi-card glass-panel rounded-2xl border border-cp-accent/20 p-5 animate-fadeIn stagger-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-cp-muted">En cours</p>
              <TrendingUp className="h-4 w-4 text-cp-accent" />
            </div>
            <p className="mt-3 font-display text-3xl font-bold text-cp-accent animate-countUp">
              {revenueToday.toLocaleString('fr-FR')}
            </p>
            <p className="mt-1 text-xs text-cp-muted">XOF en cours</p>
          </div>
        </div>
      )}

      {/* Stations table */}
      {loading ? (
        <SkeletonTable rows={6} cols={5} />
      ) : data?.empty ? (
        <div className="glass-panel flex flex-col items-center justify-center rounded-2xl border border-white/5 py-16 text-center">
          <Gamepad2 className="mb-4 h-12 w-12 text-cp-muted/50" />
          <p className="font-semibold text-cp-text">Aucune station dans votre périmètre</p>
          <p className="mt-2 max-w-sm text-sm text-cp-muted">
            Créez des salles et des stations pour voir leur état ici.
          </p>
        </div>
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
          <div className="border-b border-white/5 px-5 py-4">
            <h2 className="font-semibold">État des stations</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-5 py-3">Station</th>
                  <th className="px-5 py-3">État</th>
                  <th className="px-5 py-3">Temps restant</th>
                  <th className="px-5 py-3">Offre</th>
                  <th className="px-5 py-3">Paiement</th>
                </tr>
              </thead>
              <tbody>
                {data?.stations.map((r, i) => (
                  <tr
                    key={r.code}
                    className={`border-b border-white/5 transition hover:bg-white/[0.03] animate-fadeIn`}
                    style={{ animationDelay: `${i * 0.03}s` }}
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <StatusDot state={r.state} />
                        <div>
                          <p className="font-mono text-sm font-medium text-cp-accent">{r.code}</p>
                          <p className="text-xs text-cp-muted">{r.name}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge tone={stateTone(r.state)}>{stateLabel(r.state)}</Badge>
                    </td>
                    <td className="px-5 py-3.5">
                      {r.state === 'ACTIVE' || r.state === 'PAUSE' ? (
                        <span className="flex items-center gap-1.5 font-mono text-sm">
                          {r.state === 'ACTIVE' && <Zap className="h-3 w-3 text-cp-cyan" />}
                          {formatTimer(r.remaining_s)}
                        </span>
                      ) : (
                        <span className="text-cp-muted">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-xs">
                      {r.duration_min != null ? (
                        <span>
                          {r.duration_min} min
                          {r.price_xof != null && (
                            <span className="ml-1.5 text-cp-muted">
                              · {r.price_xof.toLocaleString('fr-FR')} XOF
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-cp-muted">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      {r.provider ? (
                        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-cp-muted">
                          {r.provider}
                        </span>
                      ) : (
                        <span className="text-cp-muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2 border-t border-white/5 px-5 py-3 text-xs text-cp-muted">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            Rafraîchissement automatique toutes les 30 secondes
          </div>
        </div>
      )}
    </div>
  )
}
