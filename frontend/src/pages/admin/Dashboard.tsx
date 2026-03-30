import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { apiGet } from '../../lib/api'

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

function stateTone(s: string): 'ok' | 'warn' | 'bad' | 'muted' {
  if (s === 'OK') return 'ok'
  if (s === 'ACTIVE') return 'warn'
  if (s === 'PENDING') return 'muted'
  if (s === 'PAUSE') return 'warn'
  return 'bad'
}

export function AdminDashboard({
  title = 'Tableau de bord',
  description = 'Vue synthétique des stations actives dans votre périmètre.',
}: {
  title?: string
  description?: string
}) {
  const [data, setData] = useState<Summary | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<Summary>('/admin/dashboard/summary')
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  return (
    <>
      <PageHeader title={title} description={description} />
      {err ? (
        <p className="text-rose-300">{err}</p>
      ) : null}
      {!data ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap gap-3">
            <Badge tone={data.paystack ? 'ok' : 'muted'}>
              Paystack {data.paystack ? 'activé' : 'off'}
            </Badge>
            <Badge tone={data.cinetpay ? 'ok' : 'muted'}>
              CinetPay {data.cinetpay ? 'activé' : 'off'}
            </Badge>
          </div>
          {data.empty ? (
            <Card>
              <p className="text-cp-muted">
                Aucune station dans votre périmètre ou aucune donnée à afficher.
              </p>
            </Card>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                    <th className="px-4 py-3">Station</th>
                    <th className="px-4 py-3">État</th>
                    <th className="px-4 py-3">Timer</th>
                    <th className="px-4 py-3">Offre</th>
                    <th className="px-4 py-3">PSP</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stations.map((r) => (
                    <tr
                      key={r.code}
                      className="border-b border-white/5 hover:bg-white/[0.03]"
                    >
                      <td className="px-4 py-3">
                        <p className="font-mono text-cp-accent">{r.code}</p>
                        <p className="text-xs text-cp-muted">{r.name}</p>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={stateTone(r.state)}>{r.state}</Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {r.remaining_s || '—'}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {r.duration_min != null ? `${r.duration_min} min` : '—'}
                        {r.price_xof != null ? (
                          <span className="text-cp-muted">
                            {' '}
                            · {r.price_xof} XOF
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 text-xs text-cp-muted">
                        {r.provider || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </>
  )
}
