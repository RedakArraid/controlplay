import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, apiPutJson } from '../../lib/api'

type Row = {
  id: number
  name: string
  description: string | null
  price_xof: number
  provider: string
  sort_order: number
  is_active: boolean
}

type Resp = { products: Row[] }

const emptyForm = () => ({
  name: '',
  description: '',
  price_xof: '',
  sort_order: '0',
  is_active: true,
})

export function BoutiqueProduits() {
  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(emptyForm)

  const load = useCallback(async () => {
    setErr(null)
    const r = await apiGet<Resp>('/admin/shop-products')
    setData(r)
  }, [])

  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [load])

  const startCreate = () => {
    setEditingId(null)
    setForm(emptyForm())
  }

  const startEdit = (p: Row) => {
    setEditingId(p.id)
    setForm({
      name: p.name,
      description: p.description ?? '',
      price_xof: String(p.price_xof),
      sort_order: String(p.sort_order),
      is_active: p.is_active,
    })
    setErr(null)
  }

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setErr(null)
    const price = Number(form.price_xof)
    const ord = Number(form.sort_order)
    if (!Number.isFinite(price) || price < 0) {
      setErr('Prix XOF invalide.')
      return
    }
    if (!Number.isFinite(ord)) {
      setErr('Ordre d’affichage invalide.')
      return
    }
    try {
      setSaving(true)
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() ? form.description.trim() : null,
        price_xof: Math.round(price),
        sort_order: Math.round(ord),
        provider: 'paystack',
        is_active: form.is_active,
      }
      if (editingId) {
        await apiPutJson(`/admin/shop-products/${editingId}`, payload)
      } else {
        await apiPostJson('/admin/shop-products', payload)
      }
      await load()
      startCreate()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const softDelete = async (id: number) => {
    if (!window.confirm('Retirer ce produit du catalogue vitrine ?')) return
    setErr(null)
    try {
      setSaving(true)
      await apiPostJson(`/admin/shop-products/${id}/delete`, {})
      await load()
      if (editingId === id) startCreate()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const rows = data?.products ?? []

  return (
    <>
      <PageHeader
        title="Produits boutique"
        description="Articles vendus en ligne (hors temps de jeu / location). Visible sur /boutique."
      />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h3 className="font-display font-semibold">
            {editingId ? `Modifier #${editingId}` : 'Nouveau produit'}
          </h3>
          <form className="mt-4 flex flex-col gap-3" onSubmit={submit}>
            <label className="text-xs font-medium uppercase text-cp-muted">Nom</label>
            <input
              required
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              disabled={saving}
            />
            <label className="text-xs font-medium uppercase text-cp-muted">Description</label>
            <textarea
              rows={3}
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-muted"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              disabled={saving}
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium uppercase text-cp-muted">Prix XOF</label>
                <input
                  required
                  type="number"
                  min={0}
                  className="mt-1 w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
                  value={form.price_xof}
                  onChange={(e) => setForm({ ...form, price_xof: e.target.value })}
                  disabled={saving}
                />
              </div>
              <div>
                <label className="text-xs font-medium uppercase text-cp-muted">Ordre</label>
                <input
                  type="number"
                  className="mt-1 w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
                  value={form.sort_order}
                  onChange={(e) => setForm({ ...form, sort_order: e.target.value })}
                  disabled={saving}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-cp-muted">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                disabled={saving}
              />
              Actif
            </label>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button type="submit" disabled={saving}>
                {editingId ? 'Enregistrer' : 'Créer'}
              </Button>
              {editingId ? (
                <Button type="button" variant="ghost" disabled={saving} onClick={startCreate}>
                  Annuler édition
                </Button>
              ) : null}
            </div>
          </form>
          {err ? <p className="mt-3 text-sm text-rose-300">{err}</p> : null}
        </Card>

        <Card className="p-6">
          <h3 className="font-display font-semibold">Catalogue ({rows.length})</h3>
          <div className="mt-4 max-h-[70vh] space-y-2 overflow-auto pr-1">
            {rows.length === 0 ? (
              <p className="text-sm text-cp-muted">Aucun article.</p>
            ) : (
              rows.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`w-full rounded-xl border px-3 py-3 text-left text-sm transition hover:bg-white/[0.06] ${editingId === r.id ? 'border-cp-amber bg-cp-amber/10' : 'border-cp-border'}`}
                  onClick={() => startEdit(r)}
                >
                  <div className="flex justify-between gap-2">
                    <span className="font-medium">{r.name}</span>
                    <span className="text-cp-muted">{r.price_xof} XOF</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <Badge tone="muted">ordre {r.sort_order}</Badge>
                    {r.is_active ? (
                      <Badge tone="ok">actif</Badge>
                    ) : (
                      <Badge tone="muted">inactif</Badge>
                    )}
                  </div>
                  <button
                    type="button"
                    className="mt-3 text-xs text-cp-danger hover:underline"
                    onClick={(e) => {
                      e.stopPropagation()
                      void softDelete(r.id)
                    }}
                  >
                    Désactiver
                  </button>
                </button>
              ))
            )}
          </div>
        </Card>
      </div>
    </>
  )
}
