import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, ApiError } from '../../lib/api'

type Offer = {
  id: number
  name: string
  duration_minutes: number
  price_xof: number
  provider: string
  attached: boolean
}

type Resp = {
  station: { id: number; code: string; name: string }
  offers: Offer[]
}

export function StationOffers() {
  const params = useParams()
  const stationId = useMemo(() => Number(params.stationId), [params.stationId])

  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  async function reload() {
    if (!Number.isFinite(stationId)) return
    const d = await apiGet<Resp>(`/admin/stations/${stationId}/offers`)
    setData(d)
    setSelected(new Set(d.offers.filter((o) => o.attached).map((o) => o.id)))
  }

  useEffect(() => {
    reload().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stationId])

  async function save() {
    if (!data) return
    setErr(null)
    setSaving(true)
    try {
      const r = await fetch(`/api/admin/stations/${stationId}/offers`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offer_ids: [...selected] }),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
      }
      await reload()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        title={data ? `Offres — ${data.station.name}` : 'Offres — station'}
        description="Attachez / détachez des offres (templates) à cette station."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!data ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <Card className="overflow-x-auto p-0">
          <div className="p-6">
            <div className="mb-4 text-sm text-cp-muted">
              {data.station.code} · {data.station.id}
            </div>
            <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
              <p className="text-cp-muted">{selected.size} offre(s) attachée(s)</p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                    <th className="px-4 py-3">Nom</th>
                    <th className="px-4 py-3">Durée</th>
                    <th className="px-4 py-3">Prix</th>
                    <th className="px-4 py-3">Provider</th>
                    <th className="px-4 py-3">Attacher</th>
                  </tr>
                </thead>
                <tbody>
                  {data.offers.length === 0 ? (
                    <tr>
                      <td className="px-4 py-6 text-cp-muted" colSpan={5}>
                        Aucune offre disponible (périmètre / droits).
                      </td>
                    </tr>
                  ) : (
                    data.offers.map((o) => {
                      const isOn = selected.has(o.id)
                      return (
                        <tr
                          key={o.id}
                          className="border-b border-white/5 hover:bg-white/[0.03]"
                        >
                          <td className="px-4 py-3 font-medium">{o.name}</td>
                          <td className="px-4 py-3 font-mono text-xs">
                            {o.duration_minutes} min
                          </td>
                          <td className="px-4 py-3 font-mono text-xs">
                            {o.price_xof} XOF
                          </td>
                          <td className="px-4 py-3 text-xs text-cp-muted">
                            {o.provider}
                          </td>
                          <td className="px-4 py-3">
                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={isOn}
                                onChange={(e) => {
                                  const next = new Set(selected)
                                  if (e.target.checked) next.add(o.id)
                                  else next.delete(o.id)
                                  setSelected(next)
                                }}
                              />
                              Attacher
                            </label>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button onClick={save} disabled={saving || !data}>
                {saving ? 'Enregistrement…' : 'Enregistrer les attaches'}
              </Button>
              <a
                href="/admin/stations"
                className="text-sm text-cp-teal hover:underline"
              >
                ← Retour aux stations
              </a>
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

