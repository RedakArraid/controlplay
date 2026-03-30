import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { apiGet, ApiError } from '../../lib/api'

type Row = {
  id: number
  code: string
  name: string
  broadlink_ip: string
  tv_size_inches: number | null
  console_model: string | null
  vr_headset_model: string | null
  salle_code: string
  is_active: boolean
}

export function Stations() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [salles, setSalles] = useState<{ id: number; code: string; name: string }[]>(
    [],
  )
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | 'new' | null>(null)

  const [newForm, setNewForm] = useState({
    code: '',
    name: '',
    broadlink_ip: '',
    salle_code: '',
    tv_size_inches: '',
    console_model: '',
    vr_headset_model: '',
    is_active: true,
  })

  const [editForm, setEditForm] = useState<Record<number, typeof newForm>>({})

  function parseNullableInt(v: string): number | null {
    const t = v.trim()
    if (!t) return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
  }

  useEffect(() => {
    ;(async () => {
      try {
        const [s1, s2] = await Promise.all([
          apiGet<{ stations: Row[] }>('/admin/stations'),
          apiGet<{ salles: { id: number; code: string; name: string }[] }>(
            '/admin/salles',
          ),
        ])
        setRows(s1.stations)
        setSalles(s2.salles)
        const nextEdit: Record<number, typeof newForm> = {}
        s1.stations.forEach((st) => {
          nextEdit[st.id] = {
            code: st.code,
            name: st.name,
            broadlink_ip: st.broadlink_ip,
            salle_code: st.salle_code ?? '',
            tv_size_inches: st.tv_size_inches == null ? '' : String(st.tv_size_inches),
            console_model: st.console_model ?? '',
            vr_headset_model: st.vr_headset_model ?? '',
            is_active: st.is_active,
          }
        })
        setEditForm(nextEdit)
      } catch (e) {
        setErr(e instanceof Error ? e.message : 'Erreur')
      }
    })()
  }, [])

  async function reload() {
    const d = await apiGet<{ stations: Row[] }>('/admin/stations')
    setRows(d.stations)
    const nextEdit: Record<number, typeof newForm> = {}
    d.stations.forEach((st) => {
      nextEdit[st.id] = {
        code: st.code,
        name: st.name,
        broadlink_ip: st.broadlink_ip,
        salle_code: st.salle_code ?? '',
        tv_size_inches: st.tv_size_inches == null ? '' : String(st.tv_size_inches),
        console_model: st.console_model ?? '',
        vr_headset_model: st.vr_headset_model ?? '',
        is_active: st.is_active,
      }
    })
    setEditForm(nextEdit)
  }

  async function createStation(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    setSaving('new')
    try {
      const r = await fetch('/api/admin/stations', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: newForm.code.trim(),
          name: newForm.name.trim(),
          broadlink_ip: newForm.broadlink_ip.trim(),
          salle_code: newForm.salle_code.trim() || null,
          tv_size_inches: parseNullableInt(newForm.tv_size_inches),
          console_model: newForm.console_model.trim() || null,
          vr_headset_model: newForm.vr_headset_model.trim() || null,
          ir_code_hdmi1: null,
          ir_code_hdmi2: null,
          is_active: newForm.is_active,
        }),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new ApiError(msg || 'Erreur', r.status)
      }
      setNewForm({
        code: '',
        name: '',
        broadlink_ip: '',
        salle_code: '',
        tv_size_inches: '',
        console_model: '',
        vr_headset_model: '',
        is_active: true,
      })
      await reload()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(null)
    }
  }

  async function updateStation(e: React.FormEvent, id: number) {
    e.preventDefault()
    const f = editForm[id]
    if (!f) return
    setErr(null)
    setSaving(id)
    try {
      const r = await fetch(`/api/admin/stations/${id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: f.code.trim(),
          name: f.name.trim(),
          broadlink_ip: f.broadlink_ip.trim(),
          salle_code: f.salle_code.trim() || null,
          tv_size_inches: parseNullableInt(f.tv_size_inches),
          console_model: f.console_model.trim() || null,
          vr_headset_model: f.vr_headset_model.trim() || null,
          ir_code_hdmi1: null,
          ir_code_hdmi2: null,
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

  return (
    <>
      <PageHeader
        title="Stations"
        description="Stations et rattachement salle (édition code / IP / active)."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <>
          <Card className="mb-6">
            <h2 className="mb-4 text-base font-semibold">Créer une station</h2>
            <form className="grid gap-3 md:grid-cols-7" onSubmit={createStation}>
              <input
                required
                placeholder="Code"
                value={newForm.code}
                onChange={(e) => setNewForm((s) => ({ ...s, code: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono"
              />
              <input
                required
                placeholder="Nom"
                value={newForm.name}
                onChange={(e) => setNewForm((s) => ({ ...s, name: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                required
                placeholder="Broadlink IP"
                value={newForm.broadlink_ip}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, broadlink_ip: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono"
              />
              <input
                placeholder="TV pouces (optionnel)"
                value={newForm.tv_size_inches}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, tv_size_inches: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono"
              />
              <input
                placeholder="Console (ex: PS5)"
                value={newForm.console_model}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, console_model: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <input
                placeholder="VR (ex: Quest 3)"
                value={newForm.vr_headset_model}
                onChange={(e) =>
                  setNewForm((s) => ({ ...s, vr_headset_model: e.target.value }))
                }
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              />
              <select
                value={newForm.salle_code}
                onChange={(e) => setNewForm((s) => ({ ...s, salle_code: e.target.value }))}
                className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              >
                <option value="">(sans salle)</option>
                {salles.map((s) => (
                  <option key={s.id} value={s.code}>
                    {s.code} — {s.name}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm text-cp-muted">
                <input
                  type="checkbox"
                  checked={newForm.is_active}
                  onChange={(e) => setNewForm((s) => ({ ...s, is_active: e.target.checked }))}
                />
                Active
              </label>
              <div className="md:col-span-7">
                <Button type="submit" disabled={saving === 'new'}>
                  {saving === 'new' ? 'Création…' : 'Créer la station'}
                </Button>
              </div>
            </form>
          </Card>

          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[1080px] text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Nom</th>
                  <th className="px-4 py-3">Salle</th>
                  <th className="px-4 py-3">Broadlink</th>
                  <th className="px-4 py-3">TV</th>
                  <th className="px-4 py-3">Console</th>
                  <th className="px-4 py-3">VR</th>
                  <th className="px-4 py-3">Actif</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-white/5 hover:bg-white/[0.03]"
                  >
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
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={editForm[r.id]?.salle_code ?? ''}
                        onChange={(e) =>
                          setEditForm((s) => ({
                            ...s,
                            [r.id]: { ...s[r.id], salle_code: e.target.value },
                          }))
                        }
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                      >
                        <option value="">(sans salle)</option>
                        {salles.map((s) => (
                          <option key={s.id} value={s.code}>
                            {s.code}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <input
                        value={editForm[r.id]?.broadlink_ip ?? ''}
                        onChange={(e) =>
                          setEditForm((s) => ({
                            ...s,
                            [r.id]: {
                              ...s[r.id],
                              broadlink_ip: e.target.value,
                            },
                          }))
                        }
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 font-mono text-xs text-cp-muted"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        value={editForm[r.id]?.tv_size_inches ?? ''}
                        onChange={(e) =>
                          setEditForm((s) => ({
                            ...s,
                            [r.id]: { ...s[r.id], tv_size_inches: e.target.value },
                          }))
                        }
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 font-mono text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        value={editForm[r.id]?.console_model ?? ''}
                        onChange={(e) =>
                          setEditForm((s) => ({
                            ...s,
                            [r.id]: {
                              ...s[r.id],
                              console_model: e.target.value,
                            },
                          }))
                        }
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        value={editForm[r.id]?.vr_headset_model ?? ''}
                        onChange={(e) =>
                          setEditForm((s) => ({
                            ...s,
                            [r.id]: {
                              ...s[r.id],
                              vr_headset_model: e.target.value,
                            },
                          }))
                        }
                        className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1.5 text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={r.is_active ? 'ok' : 'muted'}>
                        {r.is_active ? 'oui' : 'non'}
                      </Badge>
                      <div className="mt-2">
                        <label className="flex items-center gap-2 text-xs text-cp-muted">
                          <input
                            type="checkbox"
                            checked={editForm[r.id]?.is_active ?? false}
                            onChange={(e) =>
                              setEditForm((s) => ({
                                ...s,
                                [r.id]: {
                                  ...s[r.id],
                                  is_active: e.target.checked,
                                },
                              }))
                            }
                          />
                          Actif
                        </label>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <a
                        className="text-cp-teal hover:underline"
                        href={`/s/${encodeURIComponent(r.code)}`}
                      >
                        /s/{r.code}
                      </a>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <a
                          className="text-cp-teal hover:underline"
                          href={`/admin/stations/${r.id}/offers`}
                        >
                          Offres
                        </a>
                        <form onSubmit={(e) => updateStation(e, r.id)}>
                          <Button
                            type="submit"
                            variant="secondary"
                            disabled={saving === r.id}
                          >
                            {saving === r.id ? '...' : 'Enregistrer'}
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
