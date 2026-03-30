import { useEffect, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/Badge'
import { apiGet, apiPutJson } from '../../lib/api'
import type { AdminBootstrap, AuthMe } from '../../types'

type Detail = {
  user: {
    id: number
    name: string
    email: string | null
    phone: string | null
    is_active: boolean
    created_by_user_id?: number | null
    created_by?: { id: number; name: string; email: string | null; phone: string | null } | null
  }
  global_roles: string[]
  salle_assignments: {
    salle_id: number
    code: string
    name: string
    role: string
  }[]
  salles: { id: number; code: string; name: string }[]
  editable_salle_roles: { key: string; label: string }[]
  removable_global_roles: string[]
  viewer_can_manage_super_admins?: boolean
}

type OutletCtx = { me: AuthMe; boot: AdminBootstrap | null }

function StaffDelegationEditor({ userId }: { userId: number }) {
  const [keys, setKeys] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    apiGet<{ keys: string[] }>(`/super-admin/staff/${userId}/permissions`)
      .then((r) => setKeys(r.keys))
      .catch(() => setMsg('Impossible de charger les permissions'))
      .finally(() => setLoading(false))
  }, [userId])

  const toggle = (k: string) => {
    setKeys((prev) => (prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k]))
  }

  const save = () => {
    setSaving(true)
    setMsg(null)
    apiPutJson<{ ok: boolean }>(`/super-admin/staff/${userId}/permissions`, { keys })
      .then(() => setMsg('Enregistré.'))
      .catch((e) => setMsg(e instanceof Error ? e.message : 'Erreur'))
      .finally(() => setSaving(false))
  }

  if (loading) {
    return <p className="text-sm text-cp-muted">Chargement des délégations…</p>
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="text-cp-muted">
        Accès équipe ControlPlay : <code className="text-cp-accent">operations</code> (salles / stations /
        offres) et <code className="text-cp-accent">users</code> (comptes hors super administrateurs).
      </p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={keys.includes('operations')}
          onChange={() => toggle('operations')}
        />
        Opérations plateforme
      </label>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={keys.includes('users')}
          onChange={() => toggle('users')}
        />
        Gestion des comptes
      </label>
      <Button type="button" variant="secondary" disabled={saving} onClick={() => void save()}>
        {saving ? 'Enregistrement…' : 'Enregistrer les délégations'}
      </Button>
      {msg ? <p className="text-xs text-cp-muted">{msg}</p> : null}
    </div>
  )
}

export function SuperUserRoles() {
  const { me } = useOutletContext<OutletCtx>()
  const { userId } = useParams()
  const id = Number(userId)
  const [data, setData] = useState<Detail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [salleId, setSalleId] = useState('')
  const [roleKey, setRoleKey] = useState('responsable')

  const canManageSuper = me.is_super_admin

  useEffect(() => {
    if (!userId || Number.isNaN(id)) return
    apiGet<Detail>(`/super-admin/users/${id}/roles`)
      .then((d) => {
        setData(d)
        if (d.salles.length) setSalleId(String(d.salles[0].id))
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [userId, id])

  if (!userId || Number.isNaN(id)) {
    return <p className="text-rose-300">Utilisateur invalide</p>
  }

  return (
    <>
      <PageHeader
        title={data ? `Rôles — ${data.user.name}` : 'Rôles utilisateur'}
        description="Actions envoyées en POST classique (compatibilité serveur)."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!data ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <div className="space-y-6">
          <Card>
            <p className="text-sm text-cp-muted">
              #{data.user.id} · {data.user.email ?? '—'} ·{' '}
              {data.user.is_active ? 'actif' : 'inactif'}
            </p>
            <p className="mt-1 text-xs text-cp-muted">
              Créé par :{' '}
              {data.user.created_by
                ? `${data.user.created_by.name} (#${data.user.created_by.id})`
                : '—'}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {data.global_roles.map((g) => (
                <Badge key={g} tone="muted">
                  {g}
                </Badge>
              ))}
            </div>
          </Card>

          {canManageSuper ? (
            <>
              <Card>
                <h3 className="mb-4 font-semibold">Super administrateur (global)</h3>
                <div className="flex flex-wrap gap-2">
                  <form method="post" action={`/super-admin/users/${id}/roles/super-admin`}>
                    <input type="hidden" name="grant" value="1" />
                    <Button type="submit" variant="secondary">
                      Accorder
                    </Button>
                  </form>
                  <form method="post" action={`/super-admin/users/${id}/roles/super-admin`}>
                    <input type="hidden" name="grant" value="0" />
                    <Button type="submit" variant="danger">
                      Retirer
                    </Button>
                  </form>
                </div>
              </Card>

              <Card>
                <h3 className="mb-4 font-semibold">Admin de salle (global)</h3>
                <div className="flex flex-wrap gap-2">
                  <form method="post" action={`/super-admin/users/${id}/roles/global-salle-admin`}>
                    <input type="hidden" name="grant" value="1" />
                    <Button type="submit" variant="secondary">
                      Accorder
                    </Button>
                  </form>
                  <form method="post" action={`/super-admin/users/${id}/roles/global-salle-admin`}>
                    <input type="hidden" name="grant" value="0" />
                    <Button type="submit" variant="danger">
                      Retirer
                    </Button>
                  </form>
                </div>
              </Card>
            </>
          ) : null}

          {canManageSuper && data.removable_global_roles.length > 0 ? (
            <Card>
              <h3 className="mb-4 font-semibold">Retrait rôle global</h3>
              <form
                method="post"
                action={`/super-admin/users/${id}/roles/global-remove`}
                className="flex flex-wrap items-end gap-2"
              >
                <div>
                  <label className="mb-1 block text-xs text-cp-muted">role_key</label>
                  <select
                    name="role_key"
                    className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
                  >
                    {data.removable_global_roles.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </div>
                <Button type="submit" variant="danger">
                  Retirer
                </Button>
              </form>
            </Card>
          ) : null}

          {me.is_super_admin && data.global_roles.includes('admin') ? (
            <Card>
              <h3 className="mb-4 font-semibold">Délégations équipe ControlPlay</h3>
              <StaffDelegationEditor userId={id} />
            </Card>
          ) : null}

          <Card>
            <h3 className="mb-4 font-semibold">Rôle sur une salle</h3>
            <form
              method="post"
              action={`/super-admin/users/${id}/roles/salle-set`}
              className="grid gap-3 sm:grid-cols-3"
            >
              <div>
                <label className="mb-1 block text-xs text-cp-muted">Salle</label>
                <select
                  name="salle_id"
                  required
                  value={salleId}
                  onChange={(e) => setSalleId(e.target.value)}
                  className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
                >
                  {data.salles.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.code} — {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-cp-muted">Rôle</label>
                <select
                  name="role_key"
                  required
                  value={roleKey}
                  onChange={(e) => setRoleKey(e.target.value)}
                  className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
                >
                  {data.editable_salle_roles.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-end">
                <Button type="submit" className="w-full sm:w-auto">
                  Enregistrer
                </Button>
              </div>
            </form>
          </Card>

          <Card>
            <h3 className="mb-4 font-semibold">Affectations actuelles</h3>
            <ul className="space-y-2 text-sm">
              {data.salle_assignments.length === 0 ? (
                <li className="text-cp-muted">Aucune affectation par salle.</li>
              ) : (
                data.salle_assignments.map((a) => (
                  <li
                    key={`${a.salle_id}-${a.role}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/5 bg-black/20 px-3 py-2"
                  >
                    <span>
                      <span className="font-mono text-cp-accent">{a.code}</span> — {a.role}
                    </span>
                    <form method="post" action={`/super-admin/users/${id}/roles/salle-remove`}>
                      <input type="hidden" name="salle_id" value={a.salle_id} />
                      <Button type="submit" variant="ghost" className="text-xs text-rose-300">
                        Retirer
                      </Button>
                    </form>
                  </li>
                ))
              )}
            </ul>
          </Card>
        </div>
      )}
    </>
  )
}
