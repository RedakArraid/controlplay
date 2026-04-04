import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, apiPutJson } from '../../lib/api'

type Game = {
  id: number
  name: string
  genre: string | null
  platform: string | null
  is_active: boolean
}

export function RentalGames() {
  const [rows, setRows] = useState<Game[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | 'new' | null>(null)
  const [newForm, setNewForm] = useState({ name: '', genre: '', platform: '', is_active: true })
  const [edit, setEdit] = useState<Record<number, typeof newForm>>({})

  const load = useCallback(async () => {
    const d = await apiGet<{ games: Game[] }>('/admin/rental-games')
    setRows(d.games)
    const next: Record<number, typeof newForm> = {}
    d.games.forEach((g) => {
      next[g.id] = {
        name: g.name,
        genre: g.genre ?? '',
        platform: g.platform ?? '',
        is_active: g.is_active,
      }
    })
    setEdit(next)
  }, [])

  useEffect(() => {
    load().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [load])

  return (
    <>
      <PageHeader
        title="Jeux location"
        description="Catalogue de jeux disponibles pour le parc location (indépendant des offres temps de jeu en salle)."
      />
      {err ? <p className="mb-3 text-rose-300">{err}</p> : null}

      <Card className="mb-6">
        <h3 className="mb-3 font-semibold">Nouveau jeu</h3>
        <form
          className="grid gap-3 md:grid-cols-4"
          onSubmit={async (e) => {
            e.preventDefault()
            setErr(null)
            setSaving('new')
            try {
              await apiPostJson('/admin/rental-games', newForm)
              setNewForm({ name: '', genre: '', platform: '', is_active: true })
              await load()
            } catch (x) {
              setErr(x instanceof Error ? x.message : 'Erreur')
            } finally {
              setSaving(null)
            }
          }}
        >
          <input
            required
            value={newForm.name}
            onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Nom du jeu"
          />
          <input
            value={newForm.genre}
            onChange={(e) => setNewForm((f) => ({ ...f, genre: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Genre"
          />
          <input
            value={newForm.platform}
            onChange={(e) => setNewForm((f) => ({ ...f, platform: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Plateforme (PS5, Switch...)"
          />
          <label className="flex items-center gap-2 text-sm text-cp-muted">
            <input
              type="checkbox"
              checked={newForm.is_active}
              onChange={(e) => setNewForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Actif
          </label>
          <div className="md:col-span-4">
            <Button type="submit" disabled={saving === 'new'}>
              {saving === 'new' ? 'Création…' : 'Ajouter le jeu'}
            </Button>
          </div>
        </form>
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
              <th className="px-4 py-3">Nom</th>
              <th className="px-4 py-3">Genre</th>
              <th className="px-4 py-3">Plateforme</th>
              <th className="px-4 py-3">Actif</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-white/5">
                <td className="px-4 py-3">
                  <input
                    value={edit[r.id]?.name ?? ''}
                    onChange={(e) =>
                      setEdit((s) => ({ ...s, [r.id]: { ...s[r.id], name: e.target.value } }))
                    }
                    className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    value={edit[r.id]?.genre ?? ''}
                    onChange={(e) =>
                      setEdit((s) => ({ ...s, [r.id]: { ...s[r.id], genre: e.target.value } }))
                    }
                    className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                  />
                </td>
                <td className="px-4 py-3">
                  <input
                    value={edit[r.id]?.platform ?? ''}
                    onChange={(e) =>
                      setEdit((s) => ({ ...s, [r.id]: { ...s[r.id], platform: e.target.value } }))
                    }
                    className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                  />
                </td>
                <td className="px-4 py-3">
                  <label className="flex items-center gap-2 text-xs text-cp-muted">
                    <input
                      type="checkbox"
                      checked={edit[r.id]?.is_active ?? false}
                      onChange={(e) =>
                        setEdit((s) => ({ ...s, [r.id]: { ...s[r.id], is_active: e.target.checked } }))
                      }
                    />
                    Actif
                  </label>
                </td>
                <td className="px-4 py-3">
                  <Button
                    variant="secondary"
                    disabled={saving === r.id}
                    onClick={async () => {
                      const body = edit[r.id]
                      if (!body) return
                      setErr(null)
                      setSaving(r.id)
                      try {
                        await apiPutJson(`/admin/rental-games/${r.id}`, body)
                        await load()
                      } catch (x) {
                        setErr(x instanceof Error ? x.message : 'Erreur')
                      } finally {
                        setSaving(null)
                      }
                    }}
                  >
                    {saving === r.id ? '...' : 'Enregistrer'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
