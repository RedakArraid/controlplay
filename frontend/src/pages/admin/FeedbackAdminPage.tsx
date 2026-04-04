import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPutJson } from '../../lib/api'

type FeedbackRow = {
  id: number
  rating: number
  category: string
  comment: string | null
  contact_email: string | null
  contact_phone: string | null
  status: 'new' | 'in_review' | 'resolved' | 'archived'
  station_code: string | null
  session_id: number | null
  created_at: string | null
  handled_at: string | null
}

export function FeedbackAdminPage() {
  const [items, setItems] = useState<FeedbackRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<'all' | FeedbackRow['status']>('all')
  const [ratingFilter, setRatingFilter] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)

  const load = async () => {
    try {
      setErr(null)
      const q = new URLSearchParams({
        status: statusFilter,
        rating: String(ratingFilter),
        page: String(page),
        page_size: String(pageSize),
      })
      const res = await apiGet<{ items: FeedbackRow[]; total: number }>(`/admin/feedback?${q}`)
      setItems(res.items)
      setTotal(res.total)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, ratingFilter, page, pageSize])

  const setStatus = async (id: number, status: FeedbackRow['status']) => {
    try {
      setSavingId(id)
      await apiPutJson(`/admin/feedback/${id}/status`, { status })
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSavingId(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <>
      <PageHeader title="Feedback clients" description="Suivi et traitement des retours utilisateurs." />
      {err ? <p className="mb-3 text-rose-300">{err}</p> : null}

      <Card className="mb-4">
        <div className="grid gap-3 md:grid-cols-4">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as 'all' | FeedbackRow['status'])
              setPage(1)
            }}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="all">Tous statuts</option>
            <option value="new">Nouveau</option>
            <option value="in_review">En cours</option>
            <option value="resolved">Résolu</option>
            <option value="archived">Archivé</option>
          </select>
          <select
            value={String(ratingFilter)}
            onChange={(e) => {
              setRatingFilter(Number(e.target.value))
              setPage(1)
            }}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="0">Toutes notes</option>
            <option value="5">5</option>
            <option value="4">4</option>
            <option value="3">3</option>
            <option value="2">2</option>
            <option value="1">1</option>
          </select>
          <select
            value={String(pageSize)}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPage(1)
            }}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="10">10 / page</option>
            <option value="20">20 / page</option>
            <option value="50">50 / page</option>
          </select>
        </div>
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Station</th>
              <th className="px-4 py-3">Note</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Commentaire</th>
              <th className="px-4 py-3">Contact</th>
              <th className="px-4 py-3">Statut</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id} className="border-b border-white/5 align-top">
                <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                <td className="px-4 py-3 text-xs">{r.station_code ?? '—'}</td>
                <td className="px-4 py-3">{'★'.repeat(r.rating)}</td>
                <td className="px-4 py-3 text-xs">{r.category}</td>
                <td className="px-4 py-3 text-xs">{r.comment ?? '—'}</td>
                <td className="px-4 py-3 text-xs">
                  {r.contact_email ?? r.contact_phone ? (
                    <span>{r.contact_email ?? ''} {r.contact_phone ?? ''}</span>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-4 py-3 text-xs">{r.status}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={savingId === r.id}
                      onClick={() => void setStatus(r.id, 'in_review')}
                    >
                      En cours
                    </Button>
                    <Button
                      type="button"
                      disabled={savingId === r.id}
                      onClick={() => void setStatus(r.id, 'resolved')}
                    >
                      Résolu
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={savingId === r.id}
                      onClick={() => void setStatus(r.id, 'archived')}
                    >
                      Archiver
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-3 flex items-center justify-between text-xs text-cp-muted">
        <span>{total} feedback(s) · page {page}/{totalPages}</span>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-cp-border px-2 py-1 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Précédent
          </button>
          <button
            type="button"
            className="rounded border border-cp-border px-2 py-1 disabled:opacity-40"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Suivant
          </button>
        </div>
      </div>
    </>
  )
}
