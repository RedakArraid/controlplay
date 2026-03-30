import { type FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Badge } from '../../components/Badge'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, apiPutJson } from '../../lib/api'

function csvEscape(cell: string): string {
  if (/[",\n\r]/.test(cell)) return `"${cell.replace(/"/g, '""')}"`
  return cell
}

function downloadCsv(filename: string, rows: string[][]) {
  const bom = '\uFEFF'
  const content = rows.map((r) => r.map(csvEscape).join(',')).join('\r\n')
  const blob = new Blob([bom + content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function downloadTxt(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

type Row = {
  id: number
  name: string
  email: string | null
  phone: string | null
  is_active: boolean
  created_by: { id: number; name: string; email: string | null; phone: string | null } | null
  global_roles: string[]
  salle_roles: { code: string; role: string }[]
}

type SortKey = 'id' | 'name' | 'email' | 'creator'

type PasswordResetRow = {
  user_id: number
  name: string
  email: string | null
  phone: string | null
  password: string
}

type UsersResponse = {
  users: Row[]
  total: number
  page: number
  page_size: number
  creator_options: { id: number; label: string }[]
}

export function SuperUsers() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [totalRows, setTotalRows] = useState(0)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [roleFilter, setRoleFilter] = useState('all')
  const [creatorFilter, setCreatorFilter] = useState('all')
  const [sortBy, setSortBy] = useState<SortKey>('id')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [editing, setEditing] = useState<Row | null>(null)
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    is_active: true,
  })
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    password: '',
    roleAdmin: false,
    roleSalleAdmin: false,
  })
  const [passwordResetResults, setPasswordResetResults] = useState<PasswordResetRow[] | null>(null)
  const [creatorOptions, setCreatorOptions] = useState<{ id: number; label: string }[]>([])

  const load = () => {
    const params = new URLSearchParams({
      q,
      status: statusFilter,
      role: roleFilter,
      creator: creatorFilter,
      sort_by: sortBy,
      sort_dir: sortDir,
      page: String(page),
      page_size: String(pageSize),
    })
    return apiGet<UsersResponse>(`/super-admin/users?${params.toString()}`)
      .then((d) => {
        setRows(d.users)
        setTotalRows(d.total)
        setCreatorOptions(d.creator_options)
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, statusFilter, roleFilter, creatorFilter, sortBy, sortDir, page, pageSize])

  const toggleActive = async (u: Row) => {
    try {
      setSaving(true)
      await apiPutJson<{ ok: boolean }>(`/super-admin/users/${u.id}/status`, {
        is_active: !u.is_active,
      })
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const createUser = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    try {
      setSaving(true)
      setErr(null)
      const roles: string[] = []
      if (form.roleAdmin) roles.push('admin')
      if (form.roleSalleAdmin) roles.push('salle_admin')
      await apiPostJson<{ ok: boolean; user_id: number }>('/super-admin/users', {
        name: form.name,
        email: form.email || null,
        phone: form.phone || null,
        password: form.password,
        is_active: true,
        global_roles: roles,
      })
      setForm({
        name: '',
        email: '',
        phone: '',
        password: '',
        roleAdmin: false,
        roleSalleAdmin: false,
      })
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize))
  const clampedPage = Math.min(page, totalPages)
  const pagedRows = rows ?? []

  useEffect(() => {
    setPage(1)
  }, [q, statusFilter, roleFilter, creatorFilter, sortBy, sortDir, pageSize])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const openEdit = (u: Row) => {
    setEditing(u)
    setEditForm({
      name: u.name,
      email: u.email ?? '',
      phone: u.phone ?? '',
      password: '',
      is_active: u.is_active,
    })
  }

  const toggleOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const toggleAllPage = () => {
    const pageIds = pagedRows.map((u) => u.id)
    const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id))
    if (allSelected) {
      setSelectedIds((prev) => prev.filter((id) => !pageIds.includes(id)))
      return
    }
    setSelectedIds((prev) => Array.from(new Set([...prev, ...pageIds])))
  }

  const bulkSetStatus = async (isActive: boolean) => {
    if (!selectedIds.length) return
    try {
      setSaving(true)
      await apiPutJson<{ ok: boolean; updated: number }>('/super-admin/users/bulk-status', {
        user_ids: selectedIds,
        is_active: isActive,
      })
      setSelectedIds([])
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const exportFilteredCsv = async () => {
    const params = new URLSearchParams({
      q,
      status: statusFilter,
      role: roleFilter,
      creator: creatorFilter,
      sort_by: sortBy,
      sort_dir: sortDir,
      page: '1',
      page_size: '200',
    })
    const dataResp = await apiGet<UsersResponse>(`/super-admin/users?${params.toString()}`)
    const header = [
      'id',
      'name',
      'email',
      'phone',
      'is_active',
      'global_roles',
      'salle_roles',
      'created_by_id',
      'created_by_name',
    ]
    const data = dataResp.users.map((u) => [
      String(u.id),
      u.name,
      u.email ?? '',
      u.phone ?? '',
      u.is_active ? '1' : '0',
      u.global_roles.join(';'),
      u.salle_roles.map((s) => `${s.code}:${s.role}`).join(';'),
      u.created_by ? String(u.created_by.id) : '',
      u.created_by?.name ?? '',
    ])
    downloadCsv(`utilisateurs-${new Date().toISOString().slice(0, 10)}.csv`, [header, ...data])
  }

  const bulkPasswordReset = async () => {
    if (!selectedIds.length) return
    if (
      !window.confirm(
        `Réinitialiser le mot de passe pour ${selectedIds.length} compte(s) ? Les nouveaux mots de passe seront affichés une seule fois.`
      )
    ) {
      return
    }
    try {
      setSaving(true)
      setErr(null)
      const res = await apiPostJson<{ ok: boolean; results: PasswordResetRow[] }>(
        '/super-admin/users/bulk-password-reset',
        { user_ids: selectedIds }
      )
      setPasswordResetResults(res.results)
      setSelectedIds([])
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  const saveEdit = async (ev: FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    if (!editing) return
    try {
      setSaving(true)
      await apiPutJson<{ ok: boolean }>(`/super-admin/users/${editing.id}`, {
        name: editForm.name,
        email: editForm.email || null,
        phone: editForm.phone || null,
        password: editForm.password || null,
        is_active: editForm.is_active,
      })
      setEditing(null)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Utilisateurs globaux"
        description="Création de comptes + édition des rôles par utilisateur."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      <Card className="mb-5">
        <h3 className="mb-3 font-semibold">Créer un utilisateur</h3>
        <form onSubmit={createUser} className="grid gap-3 md:grid-cols-2">
          <input
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Nom"
          />
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Email (optionnel)"
          />
          <input
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Téléphone (optionnel)"
          />
          <input
            required
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Mot de passe"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.roleAdmin}
              onChange={(e) => setForm((f) => ({ ...f, roleAdmin: e.target.checked }))}
            />
            Rôle global admin (équipe ControlPlay)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.roleSalleAdmin}
              onChange={(e) => setForm((f) => ({ ...f, roleSalleAdmin: e.target.checked }))}
            />
            Rôle global salle_admin (client)
          </label>
          <div className="md:col-span-2">
            <Button type="submit" disabled={saving}>
              {saving ? 'En cours…' : 'Créer'}
            </Button>
          </div>
        </form>
      </Card>
      <Card className="mb-5">
        <h3 className="mb-3 font-semibold">Filtres</h3>
        <div className="grid gap-3 md:grid-cols-4">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Recherche (nom, email, rôle, salle...)"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'inactive')}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="all">Tous statuts</option>
            <option value="active">Actifs</option>
            <option value="inactive">Inactifs</option>
          </select>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="all">Tous rôles globaux</option>
            <option value="super_admin">super_admin</option>
            <option value="admin">admin</option>
            <option value="salle_admin">salle_admin</option>
            <option value="manager">manager</option>
            <option value="responsable">responsable</option>
            <option value="joueur">joueur</option>
          </select>
          <select
            value={creatorFilter}
            onChange={(e) => setCreatorFilter(e.target.value)}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="all">Tous créateurs</option>
            <option value="none">Sans créateur</option>
            {creatorOptions.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.label}
              </option>
            ))}
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="id">Tri par ID</option>
            <option value="name">Tri par nom</option>
            <option value="email">Tri par email</option>
            <option value="creator">Tri par créateur</option>
          </select>
          <select
            value={sortDir}
            onChange={(e) => setSortDir(e.target.value as 'asc' | 'desc')}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="desc">Desc</option>
            <option value="asc">Asc</option>
          </select>
          <select
            value={String(pageSize)}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="10">10 / page</option>
            <option value="20">20 / page</option>
            <option value="50">50 / page</option>
          </select>
          <div className="flex items-end md:col-span-2">
            <Button
              type="button"
              variant="secondary"
              disabled={!rows || rows.length === 0}
              onClick={() => void exportFilteredCsv()}
            >
              Exporter CSV (filtre actuel)
            </Button>
          </div>
        </div>
      </Card>
      {!rows ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[1100px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-cp-muted">
                <th className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={pagedRows.length > 0 && pagedRows.every((u) => selectedIds.includes(u.id))}
                    onChange={toggleAllPage}
                  />
                </th>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Créé par</th>
                <th className="px-4 py-3">Rôles globaux</th>
                <th className="px-4 py-3">Salles</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pagedRows.map((u) => (
                <tr
                  key={u.id}
                  className="border-b border-white/5 align-top hover:bg-white/[0.03]"
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(u.id)}
                      onChange={() => toggleOne(u.id)}
                    />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{u.id}</td>
                  <td className="px-4 py-3">{u.name}</td>
                  <td className="px-4 py-3 text-xs">{u.email ?? '—'}</td>
                  <td className="px-4 py-3 text-xs text-cp-muted">
                    {u.created_by ? `${u.created_by.name} (#${u.created_by.id})` : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {u.global_roles.map((g) => (
                        <Badge key={g} tone="muted">
                          {g}
                        </Badge>
                      ))}
                      {!u.is_active ? (
                        <Badge tone="bad">inactif</Badge>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-cp-muted">
                    {u.salle_roles.length
                      ? u.salle_roles.map((s) => `${s.code}:${s.role}`).join(', ')
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-3 text-xs">
                      <Link
                        className="text-cp-teal hover:underline"
                        to={`/super-admin/users/${u.id}/roles`}
                      >
                        Éditer rôles
                      </Link>
                      <button
                        type="button"
                        onClick={() => openEdit(u)}
                        className="text-cp-cyan hover:underline"
                        disabled={saving}
                      >
                        Modifier
                      </button>
                      <button
                        type="button"
                        onClick={() => void toggleActive(u)}
                        className="text-amber-300 hover:underline"
                        disabled={saving}
                      >
                        {u.is_active ? 'Désactiver' : 'Activer'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {rows ? (
        <div className="mt-3 flex items-center justify-between text-xs text-cp-muted">
          <span>
            {totalRows} résultat(s) · page {clampedPage}/{totalPages}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded border border-cp-border px-2 py-1 disabled:opacity-40"
              disabled={clampedPage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Précédent
            </button>
            <button
              type="button"
              className="rounded border border-cp-border px-2 py-1 disabled:opacity-40"
              disabled={clampedPage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Suivant
            </button>
          </div>
        </div>
      ) : null}
      {rows ? (
        <Card className="mt-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-cp-muted">{selectedIds.length} sélectionné(s)</span>
            <Button
              type="button"
              variant="secondary"
              disabled={saving || selectedIds.length === 0}
              onClick={() => void bulkSetStatus(true)}
            >
              Activer sélection
            </Button>
            <Button
              type="button"
              variant="danger"
              disabled={saving || selectedIds.length === 0}
              onClick={() => void bulkSetStatus(false)}
            >
              Désactiver sélection
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={saving || selectedIds.length === 0}
              onClick={() => void bulkPasswordReset()}
            >
              Nouveaux mots de passe (sélection)
            </Button>
          </div>
        </Card>
      ) : null}
      {passwordResetResults ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <Card className="max-h-[85vh] w-full max-w-2xl overflow-y-auto">
            <h3 className="mb-2 font-semibold">Mots de passe générés</h3>
            <p className="mb-3 text-xs text-cp-muted">
              Copiez ou téléchargez ce fichier maintenant : ils ne seront plus affichés.
            </p>
            <pre className="mb-3 max-h-64 overflow-auto rounded-lg border border-cp-border bg-black/40 p-3 font-mono text-xs">
              {passwordResetResults
                .map(
                  (r) =>
                    `${r.user_id}\t${r.name}\t${r.email ?? ''}\t${r.phone ?? ''}\t${r.password}`
                )
                .join('\n')}
            </pre>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                onClick={() => {
                  const text = passwordResetResults
                    .map(
                      (r) =>
                        `${r.user_id}\t${r.name}\t${r.email ?? ''}\t${r.phone ?? ''}\t${r.password}`
                    )
                    .join('\n')
                  void navigator.clipboard.writeText(text)
                }}
              >
                Copier tout
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  const text = passwordResetResults
                    .map(
                      (r) =>
                        `${r.user_id}\t${r.name}\t${r.email ?? ''}\t${r.phone ?? ''}\t${r.password}`
                    )
                    .join('\n')
                  downloadTxt(`mots-de-passe-${new Date().toISOString().slice(0, 10)}.txt`, text)
                }}
              >
                Télécharger .txt
              </Button>
              <Button type="button" variant="ghost" onClick={() => setPasswordResetResults(null)}>
                Fermer
              </Button>
            </div>
          </Card>
        </div>
      ) : null}
      {editing ? (
        <Card className="mt-5">
          <h3 className="mb-3 font-semibold">Modifier utilisateur #{editing.id}</h3>
          <form onSubmit={saveEdit} className="grid gap-3 md:grid-cols-2">
            <input
              required
              value={editForm.name}
              onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              placeholder="Nom"
            />
            <input
              type="email"
              value={editForm.email}
              onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))}
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              placeholder="Email"
            />
            <input
              value={editForm.phone}
              onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))}
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              placeholder="Téléphone"
            />
            <input
              type="password"
              value={editForm.password}
              onChange={(e) => setEditForm((f) => ({ ...f, password: e.target.value }))}
              className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
              placeholder="Nouveau mot de passe (optionnel)"
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={editForm.is_active}
                onChange={(e) => setEditForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              Compte actif
            </label>
            <div className="flex gap-2">
              <Button type="submit" disabled={saving}>
                Enregistrer
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
                Annuler
              </Button>
            </div>
          </form>
        </Card>
      ) : null}
    </>
  )
}
