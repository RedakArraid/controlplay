import { useCallback, useEffect, useState } from 'react'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'

import { Modal } from '../../components/ui/Modal'
import { SkeletonTable } from '../../components/ui/Skeleton'
import { useToast } from '../../contexts/ToastContext'
import { apiGet, ApiError } from '../../lib/api'
import { Plus, Pencil, RefreshCw, Tag, Clock } from 'lucide-react'

type Row = {
  id: number
  name: string
  duration_minutes: number
  price_xof: number
  provider: string
  is_active: boolean
}

type FormShape = {
  name: string
  duration_minutes: string
  price_xof: string
  is_active: boolean
}

const emptyForm = (): FormShape => ({
  name: '',
  duration_minutes: '',
  price_xof: '',
  is_active: true,
})

function rowToForm(r: Row): FormShape {
  return {
    name: r.name,
    duration_minutes: String(r.duration_minutes),
    price_xof: String(r.price_xof),
    is_active: r.is_active,
  }
}

function formatDuration(min: number): string {
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m === 0 ? `${h}h` : `${h}h${m}`
}

export function Offers() {
  const { success, error: toastError } = useToast()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [saving, setSaving] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [editRow, setEditRow] = useState<Row | null>(null)
  const [form, setForm] = useState<FormShape>(emptyForm())
  const [editForm, setEditForm] = useState<FormShape>(emptyForm())

  const reload = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true)
      else setRefreshing(true)
      try {
        const d = await apiGet<{ offers: Row[] }>('/admin/offers')
        setRows(d.offers)
      } catch (e) {
        toastError('Chargement échoué', e instanceof Error ? e.message : 'Erreur')
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [toastError],
  )

  useEffect(() => {
    reload()
  }, [reload])

  const buildPayload = (f: FormShape) => ({
    name: f.name.trim(),
    duration_minutes: parseInt(f.duration_minutes) || 0,
    price_xof: parseInt(f.price_xof) || 0,
    is_active: f.is_active,
  })

  const handleCreate = async () => {
    setSaving(true)
    try {
      const r = await fetch('/api/admin/offers', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(form)),
      })
      if (!r.ok) throw new ApiError(await r.text(), r.status)
      success('Offre créée', `L'offre « ${form.name} » a été créée.`)
      setCreateOpen(false)
      setForm(emptyForm())
      await reload(true)
    } catch (e) {
      toastError('Création échouée', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (!editRow) return
    setSaving(true)
    try {
      const r = await fetch(`/api/admin/offers/${editRow.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(editForm)),
      })
      if (!r.ok) throw new ApiError(await r.text(), r.status)
      success('Offre mise à jour')
      setEditRow(null)
      await reload(true)
    } catch (e) {
      toastError('Mise à jour échouée', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const OfferForm = ({ f, setF }: { f: FormShape; setF: (v: FormShape) => void }) => (
    <div className="space-y-4">
      <Input
        label="Nom de l'offre *"
        value={f.name}
        onChange={(e) => setF({ ...f, name: e.target.value })}
        placeholder="ex: Session 1h"
        required
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Durée (minutes) *"
          type="number"
          min="1"
          value={f.duration_minutes}
          onChange={(e) => setF({ ...f, duration_minutes: e.target.value })}
          placeholder="60"
          helper={
            f.duration_minutes
              ? `→ ${formatDuration(parseInt(f.duration_minutes) || 0)}`
              : undefined
          }
          required
        />
        <Input
          label="Prix (XOF) *"
          type="number"
          min="0"
          value={f.price_xof}
          onChange={(e) => setF({ ...f, price_xof: e.target.value })}
          placeholder="1000"
          helper={
            f.price_xof
              ? `${parseInt(f.price_xof).toLocaleString('fr-FR')} XOF`
              : undefined
          }
          required
        />
      </div>
      {/* Preview card */}
      {f.name && f.duration_minutes && f.price_xof && (
        <div className="rounded-2xl border border-cp-cyan/20 bg-cp-cyan/5 p-4">
          <p className="text-xs font-medium uppercase tracking-wider text-cp-cyan">Aperçu</p>
          <p className="mt-2 font-display text-lg font-bold">
            {formatDuration(parseInt(f.duration_minutes) || 0)}
          </p>
          <p className="text-sm text-cp-muted">{f.name}</p>
          <p className="mt-1 font-display text-xl font-bold">
            {parseInt(f.price_xof).toLocaleString('fr-FR')}{' '}
            <span className="text-sm font-normal text-cp-muted">XOF</span>
          </p>
        </div>
      )}
      <label className="flex cursor-pointer items-center gap-3">
        <div className="relative">
          <input
            type="checkbox"
            checked={f.is_active}
            onChange={(e) => setF({ ...f, is_active: e.target.checked })}
            className="sr-only"
          />
          <div
            className={`h-5 w-9 rounded-full transition ${f.is_active ? 'bg-cp-cyan' : 'bg-white/10'}`}
          >
            <div
              className={`mt-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${f.is_active ? 'translate-x-4' : 'translate-x-0.5'}`}
            />
          </div>
        </div>
        <span className="text-sm text-cp-muted">Offre active</span>
      </label>
    </div>
  )

  return (
    <div className="animate-fadeIn">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Offres</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Créneaux de temps de jeu avec leur tarif.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => reload(true)}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-cp-muted transition hover:bg-white/10 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <Button
            onClick={() => {
              setForm(emptyForm())
              setCreateOpen(true)
            }}
          >
            <Plus className="mr-1 h-4 w-4" />
            Nouvelle offre
          </Button>
        </div>
      </div>

      {loading ? (
        <SkeletonTable rows={5} cols={5} />
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
          {!rows || rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <Tag className="mb-4 h-12 w-12 text-cp-muted/50" />
              <p className="font-semibold">Aucune offre configurée</p>
              <p className="mt-2 max-w-xs text-sm text-cp-muted">
                Créez des offres (durée + tarif) à attacher aux stations.
              </p>
              <Button className="mt-5" onClick={() => setCreateOpen(true)}>
                <Plus className="mr-1 h-4 w-4" />
                Créer une offre
              </Button>
            </div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-5 py-3">Offre</th>
                  <th className="px-5 py-3">Durée</th>
                  <th className="px-5 py-3">Prix</th>
                  <th className="px-5 py-3">Statut</th>
                  <th className="px-5 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={r.id}
                    className="border-b border-white/5 transition hover:bg-white/[0.03] animate-fadeIn"
                    style={{ animationDelay: `${i * 0.025}s` }}
                  >
                    <td className="px-5 py-3.5">
                      <p className="font-medium">{r.name}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="flex items-center gap-1.5 text-sm">
                        <Clock className="h-3.5 w-3.5 text-cp-muted" />
                        {formatDuration(r.duration_minutes)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-display font-semibold">
                        {r.price_xof.toLocaleString('fr-FR')}
                      </span>
                      <span className="ml-1 text-xs text-cp-muted">XOF</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge tone={r.is_active ? 'ok' : 'muted'}>
                        {r.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="px-5 py-3.5">
                      <button
                        onClick={() => {
                          setEditRow(r)
                          setEditForm(rowToForm(r))
                        }}
                        className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-text"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        Modifier
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Créer une offre"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Annuler
            </Button>
            <Button onClick={handleCreate} disabled={saving}>
              {saving ? 'Création…' : 'Créer'}
            </Button>
          </>
        }
      >
        <OfferForm f={form} setF={setForm} />
      </Modal>

      <Modal
        open={!!editRow}
        onClose={() => setEditRow(null)}
        title={`Modifier : ${editRow?.name ?? ''}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditRow(null)}>
              Annuler
            </Button>
            <Button onClick={handleUpdate} disabled={saving}>
              {saving ? 'Enregistrement…' : 'Enregistrer'}
            </Button>
          </>
        }
      >
        <OfferForm f={editForm} setF={setEditForm} />
      </Modal>
    </div>
  )
}
