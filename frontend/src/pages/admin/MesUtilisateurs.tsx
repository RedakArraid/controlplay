import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet } from '../../lib/api'

type UserRow = {
  id: number
  name: string
  email: string | null
  phone: string | null
  is_active: boolean
}

export function MesUtilisateurs() {
  const [rows, setRows] = useState<UserRow[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<{ users: UserRow[] }>('/admin/mes-utilisateurs')
      .then((d) => setRows(d.users))
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  return (
    <>
      <PageHeader
        title="Mes utilisateurs"
        description="Comptes que vous avez créés. Création et mise à jour via les formulaires ci-dessous."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <>
          <Card className="mb-8 overflow-x-auto p-0">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-4 py-3">ID</th>
                  <th className="px-4 py-3">Nom</th>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Tél.</th>
                  <th className="px-4 py-3">Actif</th>
                  <th className="px-4 py-3">Modifier</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b border-white/5 align-top hover:bg-white/[0.03]"
                  >
                    <td className="px-4 py-3 font-mono text-xs">{u.id}</td>
                    <td className="px-4 py-3">{u.name}</td>
                    <td className="px-4 py-3 text-xs">{u.email ?? '—'}</td>
                    <td className="px-4 py-3 text-xs">{u.phone ?? '—'}</td>
                    <td className="px-4 py-3">{u.is_active ? 'oui' : 'non'}</td>
                    <td className="px-4 py-3">
                      <form
                        method="post"
                        action={`/admin/mes-utilisateurs/${u.id}/update`}
                        className="flex flex-col gap-2"
                      >
                        <input
                          name="name"
                          defaultValue={u.name}
                          required
                          className="rounded-lg border border-cp-border bg-cp-bg/50 px-2 py-1 text-xs"
                        />
                        <label className="flex items-center gap-2 text-xs text-cp-muted">
                          <input
                            type="checkbox"
                            name="is_active"
                            value="1"
                            defaultChecked={u.is_active}
                          />
                          actif
                        </label>
                        <input
                          name="password"
                          type="password"
                          placeholder="Nouveau mdp"
                          className="rounded-lg border border-cp-border bg-cp-bg/50 px-2 py-1 text-xs"
                        />
                        <Button type="submit" variant="secondary" className="text-xs">
                          Enregistrer
                        </Button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card>
            <h3 className="mb-4 font-semibold">Créer un compte</h3>
            <p className="mb-4 text-sm text-cp-muted">
              Au moins email ou téléphone obligatoire.
            </p>
            <form
              method="post"
              action="/admin/mes-utilisateurs"
              className="grid gap-3 sm:grid-cols-2"
            >
              <input
                name="name"
                placeholder="Nom"
                required
                className="rounded-xl border border-cp-border bg-cp-bg/50 px-3 py-2 text-sm"
              />
              <input
                name="email"
                type="email"
                placeholder="Email"
                className="rounded-xl border border-cp-border bg-cp-bg/50 px-3 py-2 text-sm"
              />
              <input
                name="phone"
                placeholder="Téléphone"
                className="rounded-xl border border-cp-border bg-cp-bg/50 px-3 py-2 text-sm"
              />
              <input
                name="password"
                type="password"
                placeholder="Mot de passe"
                required
                className="rounded-xl border border-cp-border bg-cp-bg/50 px-3 py-2 text-sm"
              />
              <label className="flex items-center gap-2 text-sm text-cp-muted sm:col-span-2">
                <input type="checkbox" name="is_active" value="1" defaultChecked />
                Compte actif
              </label>
              <div className="sm:col-span-2">
                <Button type="submit">Créer</Button>
              </div>
            </form>
          </Card>
        </>
      )}
    </>
  )
}
