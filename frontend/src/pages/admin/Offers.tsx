import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, ApiError } from '../../lib/api'

type Row = {
  id: number
  name: string
  duration_minutes: number
  price_xof: number
  provider: string
  stations_n: number
  salles_n: number
}

export function Offers() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | 'new' | null>(null)

  const [newForm, setNewForm] = useState({
    name: '',
    duration_minutes: '15',
    price_xof: '100',
    is_active: true,
  })

  const [editForm, setEditForm] = useState<
    Record<
      number,
      { name: string; duration_minutes: string; price_xof: string; is_active: boolean }
    >
  >({})

  function toIntOrNull(v: string): number | null {
    const t = v.trim()
    if (!t) return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
  }

  const reload = useCallback(async () => {
    const d = await apiGet<{ offers: Row[] }>('/admin/offers')
    setRows(d.offers)
    const nextEdit: typeof editForm = {}
    d.offers.forEach((o) => {
      nextEdit[o.id] = {
        name: o.name,
        duration_minutes: String(o.duration_minutes),
        price_xof: String(o.price_xof),
        is_active: true,
      }
    })
    setEditForm(nextEdit)
  }, [])

  useEffect(() => {
    reload().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [reload])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setSaving('new')
    try {
      const duration = toIntOrNull(newForm.duration_minutes)
      const price = toIntOrNull(newForm.price_xof)
      if (duration == null || price == null) throw new Error('Durée/prix invalide')

      const r = await fetch('/api/admin/offers', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newForm.name.trim(),
          duration_minutes: duration,
          price_xof: price,
          is_active: newForm.is_active,
        }),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
      }
      setNewForm({ name: '', duration_minutes: '15', price_xof: '100', is_active: true })
      await reload()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(null)
    }
  }

  async function update(e: React.FormEvent, id: number) {
    e.preventDefault()
    const f = editForm[id]
    if (!f) return
    setErr(null)
    setSaving(id)
    try {
      const duration = toIntOrNull(f.duration_minutes)
      const price = toIntOrNull(f.price_xof)
      if (duration == null || price == null) throw new Error('Durée/prix invalide')

      const r = await fetch(`/api/admin/offers/${id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: f.name.trim(),
          duration_minutes: duration,
          price_xof: price,
          is_active: f.is_active,
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
      setSaving(null)
    }
  }

  async function del(id: number) {
    if (!confirm('Désactiver cette offre ?')) return
    setErr(null)
    setSaving(id)
    try {
      const r = await fetch(`/api/admin/offers/${id}/delete`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
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
        title="Offres"
        description="Offres templates (durée / prix). Edition en SPA via endpoints JSON."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <>
          <Card className="mb-6">
            <h2 className="mb-4 text-base font-semibold">Créer une offre</h2>
            <form className="grid gap-3 md:grid-cols-5" onSubmit={create}>
              <input
                required
                placeholder="Nom offre"
                value={newForm.name}
                onChange={(e) => setNewForm((s) => ({ ...s, name: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                required
                inputMode="numeric"
                placeholder="Durée minutes"
                value={newForm.duration_minutes}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, duration_minutes: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono"
              />
              <input
                required
                inputMode="numeric"
                placeholder="Prix XOF"
                value={newForm.price_xof}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, price_xof: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono"
              />
              <label className="flex items-center gap-2 text-sm text-cp-muted md:col-span-2">
                <input
                  type="checkbox"
                  checked={newForm.is_active}
                  onChange={(e) => setNewForm((s) => ({ ...s, is_active: e.target.checked }))}
                />
                Active
              </label>
              <div className="md:col-span-5">
                <Button type="submit" disabled={saving === 'new'}>
                  {saving === 'new' ? 'Création…' : 'Créer'}
                </Button>
              </div>
            </form>
          </Card>

          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[900px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Durée</th>
                <th className="px-4 py-3">Prix</th>
                <th className="px-4 py-3">PSP</th>
                <th className="px-4 py-3">Stations</th>
                <th className="px-4 py-3">Salles</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-white/5 hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-3 font-mono text-xs">{r.id}</td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.name ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], name: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-sm"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.duration_minutes ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], duration_minutes: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-sm font-mono"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      value={editForm[r.id]?.price_xof ?? ''}
                      onChange={(e) =>
                        setEditForm((s) => ({
                          ...s,
                          [r.id]: { ...s[r.id], price_xof: e.target.value },
                        }))
                      }
                      className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-sm font-mono"
                    />
                  </td>
                  <td className="px-4 py-3 text-xs text-cp-muted">
                    {r.provider || '—'}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{r.stations_n}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.salles_n}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <form onSubmit={(e) => update(e, r.id)}>
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-2 text-xs text-cp-muted">
                            <input
                              type="checkbox"
                              checked={editForm[r.id]?.is_active ?? true}
                              onChange={(e) =>
                                setEditForm((s) => ({
                                  ...s,
                                  [r.id]: { ...s[r.id], is_active: e.target.checked },
                                }))
                              }
                            />
                            Active
                          </label>
                          <Button type="submit" variant="secondary" disabled={saving === r.id}>
                            {saving === r.id ? '…' : 'Enregistrer'}
                          </Button>
                        </div>
                      </form>
                      <Button
                        type="button"
                        variant="danger"
                        disabled={saving === r.id}
                        className="px-3 py-2"
                        onClick={() => del(r.id)}
                      >
                        Désactiver
                      </Button>
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
