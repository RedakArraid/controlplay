import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, apiPutJson } from '../../lib/api'

type ConsoleRow = {
  id: number
  code: string
  name: string
  console_model: string | null
  controller_count: number | null
  tv_size_inches: number | null
  notes: string | null
  is_active: boolean
  game_ids: number[]
}

type Game = { id: number; name: string; is_active: boolean }

export function RentalConsoles() {
  const [rows, setRows] = useState<ConsoleRow[]>([])
  const [games, setGames] = useState<Game[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [newForm, setNewForm] = useState({
    code: '',
    name: '',
    console_model: '',
    tv_size_inches: '',
    controller_count: '',
    notes: '',
    is_active: true,
  })
  const [edit, setEdit] = useState<
    Record<
      number,
      {
        code: string
        name: string
        console_model: string
        tv_size_inches: string
        controller_count: string
        notes: string
        is_active: boolean
      }
    >
  >({})
  const [selected, setSelected] = useState<Record<number, Set<number>>>({})

  const load = useCallback(async () => {
    const d = await apiGet<{ consoles: ConsoleRow[]; games: Game[] }>('/admin/rental-consoles')
    setRows(d.consoles)
    setGames(d.games)
    const next: Record<number, Set<number>> = {}
    d.consoles.forEach((c) => {
      next[c.id] = new Set(c.game_ids)
    })
    setSelected(next)
    const e: typeof edit = {}
    d.consoles.forEach((c) => {
      e[c.id] = {
        code: c.code,
        name: c.name,
        console_model: c.console_model ?? '',
        tv_size_inches: c.tv_size_inches == null ? '' : String(c.tv_size_inches),
        controller_count: c.controller_count == null ? '' : String(c.controller_count),
        notes: c.notes ?? '',
        is_active: c.is_active,
      }
    })
    setEdit(e)
  }, [])

  useEffect(() => {
    load().catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [load])

  return (
    <>
      <PageHeader
        title="Consoles location"
        description="Associez les jeux du catalogue aux consoles location (totalement indépendant des salles de jeu)."
      />
      {err ? <p className="mb-3 text-rose-300">{err}</p> : null}
      <Card className="mb-6">
        <h3 className="mb-3 font-semibold">Nouvelle console location</h3>
        <form
          className="grid gap-3 md:grid-cols-3"
          onSubmit={async (e) => {
            e.preventDefault()
            setErr(null)
            try {
              await apiPostJson('/admin/rental-consoles', {
                ...newForm,
                tv_size_inches: newForm.tv_size_inches ? Number(newForm.tv_size_inches) : null,
                controller_count: newForm.controller_count ? Number(newForm.controller_count) : null,
              })
            } catch (x) {
              setErr(x instanceof Error ? x.message : 'Erreur')
              return
            }
            setNewForm({
              code: '',
              name: '',
              console_model: '',
              tv_size_inches: '',
              controller_count: '',
              notes: '',
              is_active: true,
            })
            await load()
          }}
        >
          <input required placeholder="Code" value={newForm.code} onChange={(e) => setNewForm((s) => ({ ...s, code: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm font-mono" />
          <input required placeholder="Nom" value={newForm.name} onChange={(e) => setNewForm((s) => ({ ...s, name: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm" />
          <input placeholder="Console (PS5...)" value={newForm.console_model} onChange={(e) => setNewForm((s) => ({ ...s, console_model: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm" />
          <input placeholder="TV pouces" value={newForm.tv_size_inches} onChange={(e) => setNewForm((s) => ({ ...s, tv_size_inches: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm" />
          <input placeholder="Manettes" value={newForm.controller_count} onChange={(e) => setNewForm((s) => ({ ...s, controller_count: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm" />
          <input placeholder="Notes" value={newForm.notes} onChange={(e) => setNewForm((s) => ({ ...s, notes: e.target.value }))} className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm" />
          <div className="md:col-span-3">
            <Button type="submit">Créer console</Button>
          </div>
        </form>
      </Card>

      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
              <th className="px-4 py-3">Console</th>
              <th className="px-4 py-3">Matériel</th>
              <th className="px-4 py-3">Jeux disponibles</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-white/5">
                <td className="px-4 py-3">
                  <input value={edit[r.id]?.code ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],code:e.target.value}}))} className="mb-1 w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs font-mono text-cp-accent" />
                  <input value={edit[r.id]?.name ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],name:e.target.value}}))} className="w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs" />
                </td>
                <td className="px-4 py-3 text-xs text-cp-muted">
                  <input value={edit[r.id]?.console_model ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],console_model:e.target.value}}))} className="mb-1 w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs" />
                  <div className="grid grid-cols-2 gap-1">
                    <input value={edit[r.id]?.tv_size_inches ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],tv_size_inches:e.target.value}}))} className="rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs" placeholder="TV" />
                    <input value={edit[r.id]?.controller_count ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],controller_count:e.target.value}}))} className="rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs" placeholder="Manettes" />
                  </div>
                  <input value={edit[r.id]?.notes ?? ''} onChange={(e)=>setEdit((s)=>({...s,[r.id]:{...s[r.id],notes:e.target.value}}))} className="mt-1 w-full rounded-lg border border-cp-border bg-cp-bg/60 px-2 py-1 text-xs" placeholder="Notes" />
                </td>
                <td className="px-4 py-3">
                  <div className="grid max-h-48 grid-cols-2 gap-2 overflow-auto">
                    {games.map((g) => {
                      const checked = selected[r.id]?.has(g.id) ?? false
                      return (
                        <label key={`${r.id}-${g.id}`} className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) =>
                              setSelected((s) => {
                                const curr = new Set(s[r.id] ?? [])
                                if (e.target.checked) curr.add(g.id)
                                else curr.delete(g.id)
                                return { ...s, [r.id]: curr }
                              })
                            }
                          />
                          {g.name}
                        </label>
                      )
                    })}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Button
                    variant="secondary"
                    disabled={savingId === r.id}
                    onClick={async () => {
                      setErr(null)
                      setSavingId(r.id)
                      try {
                        const e = edit[r.id]
                        if (e) {
                          await apiPutJson(`/admin/rental-consoles/${r.id}`, {
                            code: e.code,
                            name: e.name,
                            console_model: e.console_model || null,
                            tv_size_inches: e.tv_size_inches ? Number(e.tv_size_inches) : null,
                            controller_count: e.controller_count ? Number(e.controller_count) : null,
                            notes: e.notes || null,
                            is_active: e.is_active,
                          })
                        }
                        await apiPutJson(`/admin/rental-consoles/${r.id}/games`, {
                          game_ids: [...(selected[r.id] ?? new Set<number>())],
                        })
                        await load()
                      } catch (x) {
                        setErr(x instanceof Error ? x.message : 'Erreur')
                      } finally {
                        setSavingId(null)
                      }
                    }}
                  >
                    {savingId === r.id ? '...' : 'Enregistrer jeux'}
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
