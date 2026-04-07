import { useEffect, useRef, useState } from 'react'
import { Badge } from '../../components/Badge'
import { SkeletonTable } from '../../components/ui/Skeleton'
import { apiGet } from '../../lib/api'
import {
  Activity,
  Clock,
  Gamepad2,
  RefreshCw,
  Zap,
  CheckCircle2,
} from 'lucide-react'

type StationRow = {
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
  stations: StationRow[]
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
  const labels: Record<string, string> = {
    OK: 'Libre',
    ACTIVE: 'En jeu',
    PENDING: 'En attente',
    PAUSE: 'Pause',
  }
  return labels[s] ?? s
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
  if (isNaN(s) || s <= 0) return '0:00'
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export function StationsDashboard() {
  const [data, setData] = useState<Summary | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
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
    intervalRef.current = setInterval(() => fetchData(true), 15_000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const activeCount = data?.stations.filter((s) => s.state === 'ACTIVE').length ?? 0
  const pausedCount = data?.stations.filter((s) => s.state === 'PAUSE').length ?? 0
  const idleCount = data?.stations.filter((s) => s.state === 'OK').length ?? 0

  return (
    <div className="animate-fadeIn">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Dashboard stations</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Vue en temps réel — rafraîchissement toutes les 15 secondes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-cp-muted">
              {lastUpdated.toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </span>
          )}
          <button
            onClick={() => fetchData(true)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-text disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            Actualiser
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {err}
        </div>
      )}

      {/* Live counters */}
      {!loading && data && (
        <div className="mb-6 grid grid-cols-3 gap-3">
          <div className="glass-panel flex items-center gap-3 rounded-2xl border border-cp-cyan/20 px-4 py-3">
            <span className="status-dot active" />
            <div>
              <p className="font-display text-2xl font-bold text-cp-cyan">{activeCount}</p>
              <p className="text-xs text-cp-muted">En jeu</p>
            </div>
          </div>
          <div className="glass-panel flex items-center gap-3 rounded-2xl border border-amber-500/20 px-4 py-3">
            <span className="status-dot paused" />
            <div>
              <p className="font-display text-2xl font-bold text-amber-400">{pausedCount}</p>
              <p className="text-xs text-cp-muted">En pause</p>
            </div>
          </div>
          <div className="glass-panel flex items-center gap-3 rounded-2xl border border-emerald-500/20 px-4 py-3">
            <span className="status-dot idle" />
            <div>
              <p className="font-display text-2xl font-bold text-emerald-400">{idleCount}</p>
              <p className="text-xs text-cp-muted">Libres</p>
            </div>
          </div>
        </div>
      )}

      {/* Cards grid (real-time) */}
      {loading ? (
        <SkeletonTable rows={6} cols={4} />
      ) : data?.empty ? (
        <div className="glass-panel flex flex-col items-center justify-center rounded-2xl border border-white/5 py-16 text-center">
          <Gamepad2 className="mb-4 h-12 w-12 text-cp-muted/50" />
          <p className="font-semibold">Aucune station dans votre périmètre</p>
          <p className="mt-2 max-w-sm text-sm text-cp-muted">
            Créez des salles et des stations pour voir leur état ici.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data?.stations.map((st, i) => (
            <div
              key={st.code}
              className={`glass-panel rounded-2xl border p-4 transition animate-fadeIn ${
                st.state === 'ACTIVE'
                  ? 'border-cp-cyan/25'
                  : st.state === 'PAUSE'
                    ? 'border-amber-500/20'
                    : 'border-white/5'
              }`}
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <StatusDot state={st.state} />
                  <p className="font-mono text-xs font-semibold text-cp-accent">{st.code}</p>
                </div>
                <Badge tone={stateTone(st.state)}>{stateLabel(st.state)}</Badge>
              </div>
              <p className="mt-2 truncate text-sm font-medium">{st.name}</p>

              {(st.state === 'ACTIVE' || st.state === 'PAUSE') && (
                <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs text-cp-muted">
                      {st.state === 'ACTIVE' ? (
                        <Activity className="h-3 w-3 text-cp-cyan" />
                      ) : (
                        <Clock className="h-3 w-3 text-amber-400" />
                      )}
                      Temps restant
                    </div>
                    <span className="flex items-center gap-1 font-mono text-sm font-bold">
                      {st.state === 'ACTIVE' && <Zap className="h-3 w-3 text-cp-cyan" />}
                      {formatTimer(st.remaining_s)}
                    </span>
                  </div>
                  {st.duration_min != null && (
                    <p className="mt-1 text-xs text-cp-muted">
                      Durée: {st.duration_min} min
                      {st.price_xof != null && ` · ${st.price_xof.toLocaleString('fr-FR')} XOF`}
                    </p>
                  )}
                </div>
              )}

              {st.provider && (
                <p className="mt-2 text-xs text-cp-muted">{st.provider}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && (
        <div className="mt-4 flex items-center gap-2 text-xs text-cp-muted">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          Mise à jour automatique toutes les 15 secondes
        </div>
      )}
    </div>
  )
}
