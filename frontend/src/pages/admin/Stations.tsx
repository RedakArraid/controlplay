import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { Modal } from '../../components/ui/Modal'
import { SkeletonTable } from '../../components/ui/Skeleton'
import { useToast } from '../../contexts/ToastContext'
import { apiGet, ApiError } from '../../lib/api'
import { Plus, Pencil, ExternalLink, QrCode, RefreshCw } from 'lucide-react'

type Row = {
  id: number
  code: string
  name: string
  broadlink_ip: string | null
  usage_kind: 'game_room' | 'rental'
  tv_size_inches: number | null
  console_model: string | null
  vr_headset_model: string | null
  controller_count: number | null
  bundled_games: string | null
  salle_code: string
  is_active: boolean
}

type FormShape = {
  code: string
  name: string
  broadlink_ip: string
  salle_code: string
  tv_size_inches: string
  console_model: string
  vr_headset_model: string
  controller_count: string
  bundled_games: string
  is_active: boolean
}

const emptyForm = (): FormShape => ({
  code: '',
  name: '',
  broadlink_ip: '',
  salle_code: '',
  tv_size_inches: '',
  console_model: '',
  vr_headset_model: '',
  controller_count: '',
  bundled_games: '',
  is_active: true,
})

function rowToForm(st: Row): FormShape {
  return {
    code: st.code,
    name: st.name,
    broadlink_ip: st.broadlink_ip ?? '',
    salle_code: st.salle_code ?? '',
    tv_size_inches: st.tv_size_inches == null ? '' : String(st.tv_size_inches),
    console_model: st.console_model ?? '',
    vr_headset_model: st.vr_headset_model ?? '',
    controller_count: st.controller_count == null ? '' : String(st.controller_count),
    bundled_games: st.bundled_games ?? '',
    is_active: st.is_active,
  }
}

function parseNullableInt(v: string): number | null {
  const t = v.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function payloadFromForm(f: FormShape) {
  return {
    code: f.code.trim(),
    name: f.name.trim(),
    broadlink_ip: f.broadlink_ip.trim() || null,
    usage_kind: 'game_room' as const,
    salle_code: f.salle_code.trim() || null,
    tv_size_inches: parseNullableInt(f.tv_size_inches),
    console_model: f.console_model.trim() || null,
    vr_headset_model: f.vr_headset_model.trim() || null,
    controller_count: parseNullableInt(f.controller_count),
    bundled_games: f.bundled_games.trim() || null,
    ir_code_hdmi1: null,
    ir_code_hdmi2: null,
    is_active: f.is_active,
  }
}

export function Stations() {
  const { success, error: toastError } = useToast()
  const [rows, setRows] = useState<Row[] | null>(null)
  const [salles, setSalles] = useState<{ id: number; code: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [saving, setSaving] = useState(false)

  // Modals
  const [createOpen, setCreateOpen] = useState(false)
  const [editRow, setEditRow] = useState<Row | null>(null)

  // Forms
  const [newForm, setNewForm] = useState<FormShape>(emptyForm)
  const [editForm, setEditForm] = useState<FormShape>(emptyForm)

  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const [s1, s2] = await Promise.all([
        apiGet<{ stations: Row[] }>('/admin/stations'),
        apiGet<{ salles: { id: number; code: string; name: string }[] }>('/admin/salles'),
      ])
      setRows(s1.stations)
      setSalles(s2.salles)
    } catch (e) {
      toastError('Chargement échoué', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [toastError])

  useEffect(() => {
    reload()
  }, [reload])

  const openEdit = (row: Row) => {
    setEditRow(row)
    setEditForm(rowToForm(row))
  }

  const handleCreate = async () => {
    if (!newForm.broadlink_ip.trim()) {
      toastError('Broadlink IP obligatoire', 'Renseignez l\'adresse IP Broadlink pour cette station.')
      return
    }
    setSaving(true)
    try {
      const r = await fetch('/api/admin/stations', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payloadFromForm(newForm)),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
      }
      success('Station créée', `La station « ${newForm.name} » a été créée.`)
      setCreateOpen(false)
      setNewForm(emptyForm())
      await reload(true)
    } catch (e) {
      toastError('Création échouée', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (!editRow) return
    if (!editForm.broadlink_ip.trim()) {
      toastError('Broadlink IP obligatoire', 'Renseignez l\'adresse IP Broadlink pour cette station.')
      return
    }
    setSaving(true)
    try {
      const r = await fetch(`/api/admin/stations/${editRow.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payloadFromForm(editForm)),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
      }
      success('Station mise à jour', `La station « ${editForm.name} » a été enregistrée.`)
      setEditRow(null)
      await reload(true)
    } catch (e) {
      toastError('Mise à jour échouée', e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const StationForm = ({
    form,
    setForm,
  }: {
    form: FormShape
    setForm: (f: FormShape) => void
  }) => (
    <div className="grid gap-4 sm:grid-cols-2">
      <Input
        label="Code unique *"
        value={form.code}
        onChange={(e) => setForm({ ...form, code: e.target.value })}
        placeholder="ex: ST-001"
        className="font-mono"
        required
      />
      <Input
        label="Nom affiché *"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
        placeholder="ex: Station VR 1"
        required
      />
      <Input
        label="Broadlink IP *"
        value={form.broadlink_ip}
        onChange={(e) => setForm({ ...form, broadlink_ip: e.target.value })}
        placeholder="192.168.1.xxx"
        className="font-mono"
        required
      />
      <Select
        label="Salle"
        value={form.salle_code}
        onChange={(e) => setForm({ ...form, salle_code: e.target.value })}
      >
        <option value="">(sans salle)</option>
        {salles.map((s) => (
          <option key={s.id} value={s.code}>
            {s.code} — {s.name}
          </option>
        ))}
      </Select>
      <Input
        label="Taille TV (pouces)"
        type="number"
        value={form.tv_size_inches}
        onChange={(e) => setForm({ ...form, tv_size_inches: e.target.value })}
        placeholder="55"
        className="font-mono"
      />
      <Input
        label="Console"
        value={form.console_model}
        onChange={(e) => setForm({ ...form, console_model: e.target.value })}
        placeholder="PS5, Xbox Series X…"
      />
      <Input
        label="Casque VR"
        value={form.vr_headset_model}
        onChange={(e) => setForm({ ...form, vr_headset_model: e.target.value })}
        placeholder="Meta Quest 3…"
      />
      <Input
        label="Nb. manettes"
        type="number"
        value={form.controller_count}
        onChange={(e) => setForm({ ...form, controller_count: e.target.value })}
        placeholder="2"
        className="font-mono"
      />
      <div className="sm:col-span-2">
        <p className="mb-1.5 text-xs font-medium uppercase tracking-wider text-cp-muted">
          Jeux / notes
        </p>
        <textarea
          value={form.bundled_games}
          onChange={(e) => setForm({ ...form, bundled_games: e.target.value })}
          rows={2}
          placeholder="FIFA 25, Hogwarts Legacy…"
          className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition focus:border-cp-cyan/50 focus:outline-none resize-none"
        />
      </div>
      <label className="flex items-center gap-3 cursor-pointer sm:col-span-2">
        <div className="relative">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            className="sr-only"
          />
          <div className={`h-5 w-9 rounded-full transition ${form.is_active ? 'bg-cp-cyan' : 'bg-white/10'}`}>
            <div className={`h-4 w-4 mt-0.5 rounded-full bg-white shadow transition-transform ${form.is_active ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </div>
        </div>
        <span className="text-sm text-cp-muted">Station active</span>
      </label>
    </div>
  )

  return (
    <div className="animate-fadeIn">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold">Stations</h1>
          <p className="mt-1 text-sm text-cp-muted">
            Postes « salle de jeu » — pilotage Broadlink, QR code et sessions.
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
          <Button onClick={() => { setNewForm(emptyForm()); setCreateOpen(true) }}>
            <Plus className="h-4 w-4 mr-1" />
            Nouvelle station
          </Button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <SkeletonTable rows={6} cols={6} />
      ) : (
        <div className="glass-panel overflow-hidden rounded-2xl border border-white/5">
          {!rows || rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent/20 to-cp-vr/20">
                <QrCode className="h-7 w-7 text-cp-muted" />
              </div>
              <p className="font-semibold text-cp-text">Aucune station</p>
              <p className="mt-2 max-w-xs text-sm text-cp-muted">
                Créez votre première station pour commencer à gérer les sessions.
              </p>
              <Button className="mt-5" onClick={() => setCreateOpen(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Créer une station
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead>
                  <tr className="border-b border-white/5 text-xs uppercase tracking-wider text-cp-muted">
                    <th className="px-5 py-3">Code</th>
                    <th className="px-5 py-3">Nom</th>
                    <th className="px-5 py-3">Salle</th>
                    <th className="px-5 py-3">Matériel</th>
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
                        <p className="font-mono text-sm font-semibold text-cp-accent">{r.code}</p>
                        {r.broadlink_ip && (
                          <p className="mt-0.5 font-mono text-xs text-cp-muted">{r.broadlink_ip}</p>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <p className="font-medium">{r.name}</p>
                      </td>
                      <td className="px-5 py-3.5 text-xs text-cp-muted">
                        {r.salle_code || '—'}
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex flex-col gap-0.5 text-xs text-cp-muted">
                          {r.console_model && <span>{r.console_model}</span>}
                          {r.tv_size_inches && <span>TV {r.tv_size_inches}"</span>}
                          {r.vr_headset_model && <span>VR: {r.vr_headset_model}</span>}
                          {r.controller_count && <span>{r.controller_count} manette(s)</span>}
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <Badge tone={r.is_active ? 'ok' : 'muted'}>
                          {r.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openEdit(r)}
                            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-text"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                            Modifier
                          </button>
                          {r.usage_kind === 'game_room' && (
                            <>
                              <Link
                                to={`/admin/stations/${r.id}/offers`}
                                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-xs text-cp-muted transition hover:bg-white/10 hover:text-cp-cyan"
                              >
                                Offres
                              </Link>
                              <a
                                href={`/s/${encodeURIComponent(r.code)}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-1 text-xs text-cp-cyan hover:underline"
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Créer une station"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Annuler
            </Button>
            <Button onClick={handleCreate} disabled={saving}>
              {saving ? 'Création…' : 'Créer la station'}
            </Button>
          </>
        }
      >
        <StationForm form={newForm} setForm={setNewForm} />
      </Modal>

      {/* Edit Modal */}
      <Modal
        open={!!editRow}
        onClose={() => setEditRow(null)}
        title={`Modifier : ${editRow?.name ?? ''}`}
        size="lg"
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
        <StationForm form={editForm} setForm={setEditForm} />
      </Modal>
    </div>
  )
}
