import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, ApiError } from '../../lib/api'

type Row = {
  id: number
  code: string
  name: string
  latitude: number | null
  longitude: number | null
}

export function Salles() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | 'new' | null>(null)
  const [newForm, setNewForm] = useState({
    code: '',
    name: '',
    latitude: '',
    longitude: '',
  })
  const [editForm, setEditForm] = useState<Record<number, typeof newForm>>({})

  async function reload() {
    const d = await apiGet<{ salles: Row[] }>('/admin/salles')
    setRows(d.salles)
    const nextEdit: Record<number, typeof newForm> = {}
    d.salles.forEach((s) => {
      nextEdit[s.id] = {
        code: s.code,
        name: s.name,
        latitude: s.latitude == null ? '' : String(s.latitude),
        longitude: s.longitude == null ? '' : String(s.longitude),
      }
    })
    setEditForm(nextEdit)
  }

  useEffect(() => {
    reload().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  function parseNum(v: string): number | null {
    const t = v.trim()
    if (!t) return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
  }

  async function submitCreate(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setSaving('new')
    try {
      await apiPostJson('/admin/salles', {
        code: newForm.code.trim(),
        name: newForm.name.trim(),
        latitude: parseNum(newForm.latitude),
        longitude: parseNum(newForm.longitude),
      })
      setNewForm({ code: '', name: '', latitude: '', longitude: '' })
      await reload()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(null)
    }
  }

  async function submitUpdate(e: React.FormEvent, id: number) {
    e.preventDefault()
    const f = editForm[id]
    if (!f) return
    setErr(null)
    setSaving(id)
    try {
      const r = await fetch(`/api/admin/salles/${id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: f.code.trim(),
          name: f.name.trim(),
          latitude: parseNum(f.latitude),
          longitude: parseNum(f.longitude),
        }),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur mise à jour', r.status)
      }
      await reload()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Salles"
        description="Salles visibles selon votre périmètre. Création et édition GPS directement en SPA."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <>
          <Card className="mb-6">
            <h2 className="mb-4 text-base font-semibold">Créer une salle</h2>
            <form className="grid gap-3 md:grid-cols-4" onSubmit={submitCreate}>
              <input
                placeholder="Code"
                required
                value={newForm.code}
                onChange={(e) => setNewForm((s) => ({ ...s, code: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                placeholder="Nom"
                required
                value={newForm.name}
                onChange={(e) => setNewForm((s) => ({ ...s, name: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                placeholder="Latitude (optionnel)"
                value={newForm.latitude}
                onChange={(e) => setNewForm((s) => ({ ...s, latitude: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                placeholder="Longitude (optionnel)"
                value={newForm.longitude}
                onChange={(e) => setNewForm((s) => ({ ...s, longitude: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <div className="md:col-span-4">
                <Button type="submit" disabled={saving === 'new'}>
                  {saving === 'new' ? 'Création…' : 'Créer la salle'}
                </Button>
              </div>
            </form>
          </Card>

          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[780px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Latitude</th>
                <th className="px-4 py-3">Longitude</th>
                  <th className="px-4 py-3">Lien</th>
                  <th className="px-4 py-3">Offres / Users</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-white/5 hover:bg-white/[0.03]">
                  <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.code ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], code: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 font-mono text-xs text-cp-accent"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.name ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], name: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.latitude ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], latitude: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 font-mono text-xs"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.longitude ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], longitude: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 font-mono text-xs"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <a
                      className="text-cp-teal hover:underline"
                      href={`/salle/${encodeURIComponent(r.code)}`}
                    >
                      Page publique
                    </a>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <a
                        className="text-cp-teal hover:underline"
                        href={`/admin/salles/${r.id}/offers`}
                      >
                        Gérer offres
                      </a>
                      <a
                        className="text-cp-teal hover:underline"
                        href={`/admin/salles/${r.id}/users`}
                      >
                        Gérer users
                      </a>
                      <form onSubmit={(e) => submitUpdate(e, r.id)}>
                        <Button type="submit" variant="secondary" disabled={saving === r.id}>
                          {saving === r.id ? '…' : 'Enregistrer GPS'}
                        </Button>
                      </form>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </Card>
        </>
      )}
    </>
  )
}
