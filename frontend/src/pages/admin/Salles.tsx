import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Modal } from '../../components/ui/Modal'
import { SkeletonTable } from '../../components/ui/Skeleton'
import { useToast } from '../../contexts/ToastContext'
import { apiGet, ApiError } from '../../lib/api'
import { Plus, Pencil, RefreshCw, MapPin } from 'lucide-react'

type Row = {
  id: number
  code: string
  name: string
  latitude: number | null
  longitude: number | null
}

type FormShape = {
  code: string
  name: string
  latitude: string
  longitude: string
}

const emptyForm = (): FormShape => ({ code: '', name: '', latitude: '', longitude: '' })

function rowToForm(r: Row): FormShape {
  return {
    code: r.code,
    name: r.name,
    latitude: r.latitude == null ? '' : String(r.latitude),
    longitude: r.longitude == null ? '' : String(r.longitude),
  }
}

export function Salles() {
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
        const d = await apiGet<{ salles: Row[] }>('/admin/salles')
        setRows(d.salles)
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

  const handleCreate = async () => {
    setSaving(true)
    try {
      const r = await fetch('/api/admin/salles', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: form.code.trim(),
          name: form.name.trim(),
          latitude: form.latitude ? parseFloat(form.latitude) : null,
          longitude: form.longitude ? parseFloat(form.longitude) : null,
        }),
      })
      if (!r.ok) throw new ApiError(await r.text(), r.status)
      success('Salle créée', `La salle « ${form.name} » a été créée.`)
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
      const r = await fetch(`/api/admin/salles/${editRow.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: editForm.code.trim(),
          name: editForm.name.trim(),
          latitude: editForm.latitude ? parseFloat(editForm.latitude) : null,
          longitude: editForm.longitude ? parseFloat(editForm.longitude) : null,
        }),
      })
      if (!r.ok) throw new ApiError(await r.text(), r.status)
      success('Salle mise à jour')
      setEditRow(null)
      await reload(true)
    } catch (e) {
      toastError('Mise à jour échouée', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const SalleForm = ({
    f,
    setF,
  }: {
    f: FormShape
    setF: (v: FormShape) => void
  }) => (
    <div className="grid gap-4 sm:grid-cols-2">
      <Input
        label="Code unique *"
        value={f.code}
        onChange={(e) => setF({ ...f, code: e.target.value })}
        placeholder="ex: SALLE-ABJ-01"
        className="font-mono"
        required
      />
      <Input
        label="Nom *"
        value={f.name}
        onChange={(e) => setF({ ...f, name: e.target.value })}
        placeholder="ex: ControlPlay Abidjan Centre"
        required
      />
      <Input
        label="Latitude"
        type="number"
        step="any"
        value={f.latitude}
        onChange={(e) => setF({ ...f, latitude: e.target.value })}
        placeholder="5.3545"
        helper="Optionnel — affichage sur la carte"
      />
      <Input
        label="Longitude"
        type="number"
        step="any"
        value={f.longitude}
        onChange={(e) => setF({ ...f, longitude: e.target.value })}
        placeholder="-4.0050"
        helper="Optionnel — affichage sur la carte"
      />
    </div>
  )

  return (
    <div className="animate-fadeIn">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Salles</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Espaces partenaires regroupant des stations de jeu.
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
            Nouvelle salle
          </Button>
        </div>
      </div>

      {loading ? (
        <SkeletonTable rows={4} cols={4} />
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
          {!rows || rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <MapPin className="mb-4 h-12 w-12 text-cp-muted/50" />
              <p className="font-semibold">Aucune salle configurée</p>
              <p className="mt-2 max-w-xs text-sm text-cp-muted">
                Créez votre première salle pour y attacher des stations et des offres.
              </p>
              <Button className="mt-5" onClick={() => setCreateOpen(true)}>
                <Plus className="mr-1 h-4 w-4" />
                Créer une salle
              </Button>
            </div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-5 py-3">Code</th>
                  <th className="px-5 py-3">Nom</th>
                  <th className="px-5 py-3">Coord.</th>
                  <th className="px-5 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={r.id}
                    className="border-b border-white/5 transition hover:bg-white/[0.03] animate-fadeIn"
                    style={{ animationDelay: `${i * 0.03}s` }}
                  >
                    <td className="px-5 py-3.5 font-mono text-sm font-semibold text-cp-accent">
                      {r.code}
                    </td>
                    <td className="px-5 py-3.5 font-medium">{r.name}</td>
                    <td className="px-5 py-3.5 text-xs text-cp-muted">
                      {r.latitude != null && r.longitude != null ? (
                        <span className="flex items-center gap-1">
                          <MapPin className="h-3.5 w-3.5" />
                          {r.latitude.toFixed(4)}, {r.longitude.toFixed(4)}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
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
                        <Link
                          to={`/admin/salles/${r.id}/offers`}
                          className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-cp-muted transition hover:text-cp-cyan"
                        >
                          Offres
                        </Link>
                        <Link
                          to={`/admin/salles/${r.id}/users`}
                          className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-cp-muted transition hover:text-cp-cyan"
                        >
                          Équipe
                        </Link>
                      </div>
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
        title="Créer une salle"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Annuler
            </Button>
            <Button onClick={handleCreate} disabled={saving}>
              {saving ? 'Création…' : 'Créer la salle'}
            </Button>
          </>
        }
      >
        <SalleForm f={form} setF={setForm} />
      </Modal>

      <Modal
        open={!!editRow}
        onClose={() => setEditRow(null)}
        title={`Modifier : ${editRow?.name ?? ''}`}
        size="md"
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
        <SalleForm f={editForm} setF={setEditForm} />
      </Modal>
    </div>
  )
}
