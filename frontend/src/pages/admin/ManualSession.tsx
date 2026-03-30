import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet } from '../../lib/api'

type Opt = { value: string; label: string }

type OptionsResp = {
  options: Opt[]
  empty: boolean
  hint_html?: string | null
}

export function ManualSession() {
  const [data, setData] = useState<OptionsResp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<OptionsResp>('/admin/manual-session-options')
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  return (
    <>
      <PageHeader
        title="Session manuelle"
        description="Démarrage immédiat sans paiement en ligne — la station doit être libre."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!data ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : data.empty && data.hint_html ? (
        <Card>
          <div
            className="prose prose-invert max-w-none text-sm text-cp-muted"
            dangerouslySetInnerHTML={{ __html: data.hint_html }}
          />
        </Card>
      ) : (
        <Card>
          <form method="post" action="/admin/manual-session" className="space-y-5">
            <div>
              <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-cp-muted">
                Station & offre
              </label>
              <select
                name="station_offer"
                required
                className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-4 py-3 text-sm"
              >
                <option value="">— Choisir —</option>
                {data.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs text-cp-muted">
                  Téléphone joueur (optionnel)
                </label>
                <input
                  name="phone"
                  type="tel"
                  placeholder="+225…"
                  className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-4 py-3 text-sm"
                />
              </div>
              <div>
                <label className="mb-2 block text-xs text-cp-muted">
                  Email joueur (optionnel)
                </label>
                <input
                  name="email"
                  type="email"
                  className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-4 py-3 text-sm"
                />
              </div>
            </div>
            <Button type="submit">Démarrer la session</Button>
          </form>
        </Card>
      )}
    </>
  )
}
