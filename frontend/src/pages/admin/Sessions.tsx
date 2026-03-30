import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { apiGet } from '../../lib/api'

type Row = {
  id: number
  payment_reference: string
  payment_provider: string
  payment_status: string
  status: string
  started_at: string | null
  end_at: string | null
}

export function Sessions() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<{ sessions: Row[] }>('/admin/sessions')
      .then((d) => setRows(d.sessions))
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  return (
    <>
      <PageHeader
        title="Sessions"
        description="Dernières sessions (100 max) dans votre périmètre."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Réf.</th>
                <th className="px-4 py-3">Statut</th>
                <th className="px-4 py-3">Paiement</th>
                <th className="px-4 py-3">PSP</th>
                <th className="px-4 py-3">Début</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-white/5 hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.payment_reference}</td>
                  <td className="px-4 py-3">
                    <Badge tone="muted">{r.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-xs">{r.payment_status}</td>
                  <td className="px-4 py-3 text-xs text-cp-muted">
                    {r.payment_provider}
                  </td>
                  <td className="px-4 py-3 text-xs text-cp-muted">
                    {r.started_at ? r.started_at.slice(0, 19) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  )
}
