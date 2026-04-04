import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, apiPutJson } from '../../lib/api'

type ConsoleOption = { id: number; code: string; name: string }
type Plan = {
  id: number
  name: string
  description: string | null
  duration_label: string
  price_xof: number
  provider: string
  rental_console_id: number | null
  rental_console_code: string | null
  is_active: boolean
}

type Resp = { plans: Plan[]; consoles: ConsoleOption[] }

const emptyForm = () => ({
  name: '',
  description: '',
  duration_label: '',
  price_xof: '',
  rental_console_id: '',
  is_active: true,
})

export function RentalPlans() {
  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(emptyForm)

  const load = useCallback(async () => {
    setErr(null)
    const r = await apiGet<Resp>('/admin/rental-plans')
    setData(r)
  }, [])

  useEffect(() => {
    void load().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [load])

  const startCreate = () => {
    setEditingId(null)
    setForm(emptyForm())
  }

  const startEdit = (p: Plan) => {
    setEditingId(p.id)
    setForm({
      name: p.name,
      description: p.description ?? '',
      duration_label: p.duration_label,
      price_xof: String(p.price_xof),
      rental_console_id: p.rental_console_id ? String(p.rental_console_id) : '',
      is_active: p.is_active,
    })
    setErr(null)
  }

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setErr(null)
    const price = Number(form.price_xof)
    if (!Number.isFinite(price) || price < 0) {
      setErr('Indiquez un prix XOF valide (nombre ≥ 0).')
      return
    }
    try {
      setSaving(true)
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() ? form.description.trim() : null,
        duration_label: form.duration_label.trim(),
        price_xof: Math.round(price),
        rental_console_id: form.rental_console_id ? Number(form.rental_console_id) : null,
        is_active: form.is_active,
      }
      if (editingId) {
        await apiPutJson(`/admin/rental-plans/${editingId}`, payload)
      } else {
        await apiPostJson('/admin/rental-plans', payload)
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
    if (!window.confirm('Désactiver ce forfait ?')) return
    setErr(null)
    try {
      setSaving(true)
      await apiPostJson(`/admin/rental-plans/${id}/delete`, {})
      await load()
      if (editingId === id) startCreate()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const plans = data?.plans ?? []
  const hasPlans = plans.length > 0

  return (
    <>
      <PageHeader
        title="Forfaits location"
        description="Prix de location console / matériel (distincts des offres « temps de jeu »). Paiement via le tunnel /rental — PSP actuellement injecté côté serveur (Paystack)."
      />
      {err ? <p className="mb-3 text-rose-300">{err}</p> : null}

      <Card className="mb-4">
        <h3 className="mb-3 font-semibold">
          {editingId ? `Modifier le forfait #${editingId}` : 'Nouveau forfait'}
        </h3>
        <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label htmlFor="rp-name" className="mb-1.5 block text-xs font-medium text-cp-muted">
              Nom
            </label>
            <input
              id="rp-name"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-text outline-none focus:border-cp-accent/50"
              placeholder="Ex. Demi-journée PS5"
              autoComplete="off"
            />
          </div>
          <div>
            <label htmlFor="rp-duration" className="mb-1.5 block text-xs font-medium text-cp-muted">
              Durée affichée
            </label>
            <input
              id="rp-duration"
              required
              value={form.duration_label}
              onChange={(e) => setForm((f) => ({ ...f, duration_label: e.target.value }))}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-text outline-none focus:border-cp-accent/50"
              placeholder="Ex. 2 heures, 1 journée…"
            />
          </div>
          <div>
            <label htmlFor="rp-price" className="mb-1.5 block text-xs font-medium text-cp-muted">
              Prix (XOF)
            </label>
            <input
              id="rp-price"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              required
              value={form.price_xof}
              onChange={(e) => setForm((f) => ({ ...f, price_xof: e.target.value }))}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-text outline-none focus:border-cp-accent/50"
              placeholder="0"
            />
          </div>
          <div className="md:col-span-2">
            <label htmlFor="rp-console" className="mb-1.5 block text-xs font-medium text-cp-muted">
              Console cible (optionnel)
            </label>
            <select
              id="rp-console"
              value={form.rental_console_id}
              onChange={(e) => setForm((f) => ({ ...f, rental_console_id: e.target.value }))}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-text outline-none focus:border-cp-accent/50"
            >
              <option value="">Toutes les consoles (forfait générique)</option>
              {(data?.consoles ?? []).map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.code} — {s.name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-cp-muted">
              Si vide, le forfait peut servir au catalogue global ; sinon il est limité à la console choisie.
            </p>
          </div>
          <div className="md:col-span-2">
            <label htmlFor="rp-desc" className="mb-1.5 block text-xs font-medium text-cp-muted">
              Description
            </label>
            <textarea
              id="rp-desc"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm text-cp-text outline-none focus:border-cp-accent/50"
              rows={2}
              placeholder="Optionnel — détail affiché côté réservation si vous l’utilisez."
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-cp-text md:col-span-2">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              className="rounded border-cp-border"
            />
            Forfait actif (visible pour de nouvelles réservations)
          </label>
          <div className="flex flex-wrap gap-2 md:col-span-2">
            <Button type="submit" disabled={saving}>
              {editingId ? 'Enregistrer' : 'Créer'}
            </Button>
            {editingId ? (
              <Button type="button" variant="ghost" onClick={startCreate} disabled={saving}>
                Annuler
              </Button>
            ) : null}
          </div>
        </form>
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[960px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Nom</th>
              <th className="px-4 py-3">Durée</th>
              <th className="px-4 py-3">Prix</th>
              <th className="px-4 py-3">PSP</th>
              <th className="px-4 py-3">Console</th>
              <th className="px-4 py-3">Statut</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {!hasPlans ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-cp-muted">
                  {data ? 'Aucun forfait. Créez-en un avec le formulaire ci-dessus.' : 'Chargement…'}
                </td>
              </tr>
            ) : (
              plans.map((p) => (
                <tr
                  key={p.id}
                  className={cnRow(p.is_active)}
                >
                  <td className="px-4 py-3 font-mono text-xs">{p.id}</td>
                  <td className="px-4 py-3 font-medium">{p.name}</td>
                  <td className="px-4 py-3 text-cp-muted">{p.duration_label}</td>
                  <td className="px-4 py-3 tabular-nums">{formatXof(p.price_xof)}</td>
                  <td className="px-4 py-3 font-mono text-xs uppercase text-cp-muted">
                    {p.provider || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-cp-muted">{p.rental_console_code ?? '—'}</td>
                  <td className="px-4 py-3">
                    {p.is_active ? (
                      <Badge tone="ok">Actif</Badge>
                    ) : (
                      <Badge tone="muted">Inactif</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-3 text-xs">
                      <button
                        type="button"
                        className="text-cp-teal hover:underline disabled:opacity-40"
                        onClick={() => startEdit(p)}
                        disabled={saving}
                      >
                        Modifier
                      </button>
                      <button
                        type="button"
                        className="text-rose-300 hover:underline disabled:opacity-40"
                        onClick={() => void softDelete(p.id)}
                        disabled={saving || !p.is_active}
                      >
                        Désactiver
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </>
  )
}

function cnRow(active: boolean) {
  return active
    ? 'border-b border-white/5 hover:bg-white/[0.03]'
    : 'border-b border-white/5 bg-white/[0.02] opacity-70 hover:bg-white/[0.04]'
}

function formatXof(n: number) {
  try {
    return `${new Intl.NumberFormat('fr-FR').format(n)} XOF`
  } catch {
    return `${n} XOF`
  }
}
