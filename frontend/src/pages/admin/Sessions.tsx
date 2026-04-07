import { useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { Select } from '../../components/ui/Select'
import { SkeletonTable } from '../../components/ui/Skeleton'
import { apiGet } from '../../lib/api'
import { Filter, Search, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'

type Row = {
  id: number
  payment_reference: string
  payment_provider: string
  payment_status: string
  status: string
  started_at: string | null
  end_at: string | null
  station_code?: string
  station_name?: string
  offer_name?: string
  customer_phone?: string
}

function sessionTone(s: string): 'ok' | 'warn' | 'bad' | 'muted' | 'info' {
  if (s === 'active') return 'info'
  if (s === 'paid') return 'ok'
  if (s === 'pending') return 'muted'
  if (s === 'paused') return 'warn'
  if (s === 'extended') return 'default' as 'ok'
  if (s === 'expired' || s === 'cancelled') return 'bad'
  return 'muted'
}

const STATUS_OPTIONS = [
  { value: '', label: 'Tous les statuts' },
  { value: 'active', label: 'Actives' },
  { value: 'paid', label: 'Payées (en attente)' },
  { value: 'pending', label: 'En attente' },
  { value: 'paused', label: 'En pause' },
  { value: 'extended', label: 'Prolongées' },
  { value: 'expired', label: 'Expirées' },
]

const PAGE_SIZE = 20

export function Sessions() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const fetchData = async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const d = await apiGet<{ sessions: Row[] }>('/admin/sessions')
      setRows(d.sessions)
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
  }, [])

  // Filtered + searched rows
  const filtered = (rows ?? []).filter((r) => {
    if (filterStatus && r.status !== filterStatus) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        r.payment_reference.toLowerCase().includes(q) ||
        (r.station_code ?? '').toLowerCase().includes(q) ||
        (r.customer_phone ?? '').includes(q)
      )
    }
    return true
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const handleFilterChange = (v: string) => {
    setFilterStatus(v)
    setPage(0)
  }
  const handleSearch = (v: string) => {
    setSearch(v)
    setPage(0)
  }

  return (
    <div className="animate-fadeIn">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Sessions</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Historique et état des sessions de jeu dans votre périmètre.
          </p>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-text disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Actualiser
        </button>
      </div>

      {err && (
        <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {err}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cp-muted" />
          <input
            type="text"
            placeholder="Référence, station, téléphone…"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-xl border border-cp-border bg-cp-bg/60 pl-9 pr-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition focus:border-cp-cyan/50 focus:outline-none focus:ring-2 focus:ring-cp-cyan/10"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-cp-muted" />
          <Select
            value={filterStatus}
            onChange={(e) => handleFilterChange(e.target.value)}
            className="min-w-[180px]"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </div>
        {rows && (
          <span className="text-xs text-cp-muted">
            {filtered.length} résultat{filtered.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <SkeletonTable rows={8} cols={6} />
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-5 py-3">ID</th>
                  <th className="px-5 py-3">Référence</th>
                  <th className="px-5 py-3">Statut</th>
                  <th className="px-5 py-3">Paiement</th>
                  <th className="px-5 py-3">PSP</th>
                  <th className="px-5 py-3">Début</th>
                  <th className="px-5 py-3">Fin</th>
                </tr>
              </thead>
              <tbody>
                {paginated.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-5 py-10 text-center text-cp-muted">
                      Aucune session trouvée
                    </td>
                  </tr>
                ) : (
                  paginated.map((r, i) => (
                    <tr
                      key={r.id}
                      className="border-b border-white/5 transition hover:bg-white/[0.03] animate-fadeIn"
                      style={{ animationDelay: `${i * 0.02}s` }}
                    >
                      <td className="px-5 py-3.5 font-mono text-xs text-cp-muted">#{r.id}</td>
                      <td className="px-5 py-3.5">
                        <span className="font-mono text-xs text-cp-text">{r.payment_reference}</span>
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone={sessionTone(r.status)}>{r.status}</Badge>
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone={r.payment_status === 'paid' ? 'ok' : 'muted'}>
                          {r.payment_status}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-cp-muted">
                          {r.payment_provider || '—'}
                        </span>
                      </td>
                      <td className="px-5 py-3.5 text-xs text-cp-muted">
                        {r.started_at ? new Date(r.started_at).toLocaleString('fr-FR') : '—'}
                      </td>
                      <td className="px-5 py-3.5 text-xs text-cp-muted">
                        {r.end_at ? new Date(r.end_at).toLocaleString('fr-FR') : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-white/5 px-5 py-3">
              <span className="text-xs text-cp-muted">
                Page {page + 1} / {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
