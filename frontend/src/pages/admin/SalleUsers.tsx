import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, ApiError } from '../../lib/api'

type Resp = {
  salle: { id: number; code: string; name: string }
  viewer: { is_super_admin: boolean; can_assign_responsable: boolean }
  users: Array<{
    id: number
    name: string
    email: string | null
    phone: string | null
    is_active: boolean
    is_manager: boolean
    is_responsable: boolean
  }>
}

export function SalleUsers() {
  const params = useParams()
  const salleId = useMemo(() => Number(params.salleId), [params.salleId])

  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [selectedManagers, setSelectedManagers] = useState<Set<number>>(
    new Set(),
  )
  const [selectedResponsables, setSelectedResponsables] = useState<Set<number>>(
    new Set(),
  )

  async function reload() {
    if (!Number.isFinite(salleId)) return
    const d = await apiGet<Resp>(`/admin/salles/${salleId}/users`)
    setData(d)
    setSelectedManagers(new Set(d.users.filter((u) => u.is_manager).map((u) => u.id)))
    setSelectedResponsables(
      new Set(d.users.filter((u) => u.is_responsable).map((u) => u.id)),
    )
  }

  useEffect(() => {
    reload().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salleId])

  async function save() {
    if (!data || !Number.isFinite(salleId)) return
    setErr(null)
    setSaving(true)
    try {
      const r = await fetch(`/api/admin/salles/${salleId}/users`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          manager_user_ids: [...selectedManagers],
          responsable_user_ids: [...selectedResponsables],
        }),
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
        title={data ? `Users — ${data.salle.name}` : 'Users — salle'}
        description="Rattachez des gérants (1 salle max) et des responsables à cette salle."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!data ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <Card className="overflow-x-auto p-0">
          <div className="p-6">
            <div className="mb-4 text-sm text-cp-muted">
              {data.salle.code} · {data.salle.id}
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
              <p className="text-cp-muted">
                {selectedManagers.size} gérant(s) · {selectedResponsables.size} responsable(s)
              </p>
              {!data.viewer.can_assign_responsable ? (
                <p className="text-rose-300">
                  Responsable : actions restreintes pour votre rôle.
                </p>
              ) : null}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[920px] text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Nom</th>
                    <th className="px-4 py-3">Email</th>
                    <th className="px-4 py-3">Téléphone</th>
                    <th className="px-4 py-3">Gérant</th>
                    <th className="px-4 py-3">Responsable</th>
                  </tr>
                </thead>
                <tbody>
                  {data.users.length === 0 ? (
                    <tr>
                      <td className="px-4 py-6 text-cp-muted" colSpan={6}>
                        Aucun user dans votre périmètre / droits.
                      </td>
                    </tr>
                  ) : (
                    data.users.map((u) => {
                      const isMgr = selectedManagers.has(u.id)
                      const isResp = selectedResponsables.has(u.id)
                      return (
                        <tr
                          key={u.id}
                          className="border-b border-white/5 hover:bg-white/[0.03]"
                        >
                          <td className="px-4 py-3 font-mono text-xs">{u.id}</td>
                          <td className="px-4 py-3">{u.name}</td>
                          <td className="px-4 py-3 text-cp-muted">
                            {u.email ?? '—'}
                          </td>
                          <td className="px-4 py-3 text-cp-muted">
                            {u.phone ?? '—'}
                          </td>
                          <td className="px-4 py-3">
                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={isMgr}
                                onChange={(e) => {
                                  const next = new Set(selectedManagers)
                                  if (e.target.checked) next.add(u.id)
                                  else next.delete(u.id)
                                  setSelectedManagers(next)
                                }}
                                disabled={!u.is_active || saving}
                              />
                              <span>Manager</span>
                            </label>
                          </td>
                          <td className="px-4 py-3">
                            <label className="flex items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={isResp}
                                onChange={(e) => {
                                  const next = new Set(selectedResponsables)
                                  if (e.target.checked) next.add(u.id)
                                  else next.delete(u.id)
                                  setSelectedResponsables(next)
                                }}
                                disabled={
                                  !data.viewer.can_assign_responsable ||
                                  !u.is_active ||
                                  saving
                                }
                              />
                              <span>Responsable</span>
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
                {saving ? 'Enregistrement…' : 'Enregistrer'}
              </Button>
              <a href="/admin/salles" className="text-sm text-cp-teal hover:underline">
                ← Retour aux salles
              </a>
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

