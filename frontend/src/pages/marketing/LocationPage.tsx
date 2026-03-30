import { useEffect, useMemo, useState } from 'react'
import { Cpu, Disc, Glasses, MonitorPlay } from 'lucide-react'
import { Card } from '../../components/Card'
import { apiGet } from '../../lib/api'

type StationOut = {
  id: number
  code: string
  name: string
  tv_size_inches: number | null
  console_model: string | null
  vr_headset_model: string | null
  games: Array<{
    id: number
    name: string
    duration_minutes: number
    price_xof: number
    provider: string
  }>
}

type Resp = {
  stations: StationOut[]
}

export function LocationPage() {
  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    apiGet<Resp>('/public/stations')
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  const consoleModels = useMemo(() => {
    const m = new Map<string, number>()
    for (const st of data?.stations ?? []) {
      if (!st.console_model) continue
      m.set(st.console_model, (m.get(st.console_model) ?? 0) + 1)
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  const vrModels = useMemo(() => {
    const m = new Map<string, number>()
    for (const st of data?.stations ?? []) {
      if (!st.vr_headset_model) continue
      m.set(st.vr_headset_model, (m.get(st.vr_headset_model) ?? 0) + 1)
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-accent">Location</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Consoles & <span className="text-gradient-brand">casques VR</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        Louez des postes dans un même lieu : chaque station déclare sa composition (TV + console/VR)
        et indique les jeux disponibles pour la session.
      </p>

      {err ? <p className="mt-6 text-rose-300">{err}</p> : null}

      <h2 className="font-display mt-16 text-2xl font-bold">Familles de consoles</h2>
      {!data ? (
        <p className="mt-8 text-cp-muted">Chargement…</p>
      ) : consoleModels.length === 0 ? (
        <p className="mt-8 text-cp-muted">Aucune console déclarée (admin : stations).</p>
      ) : (
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {consoleModels.map(([model, count]) => {
            const modelLower = model.toLowerCase()
            const Icon = modelLower.includes('playstation')
              ? Disc
              : modelLower.includes('switch')
                ? Cpu
                : MonitorPlay
            return (
              <Card key={model} className="flex gap-4 p-6">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cp-cyan/15 text-cp-cyan">
                  <Icon className="h-6 w-6" />
                </span>
                <div>
                  <h3 className="font-display text-lg font-semibold">{model}</h3>
                  <p className="mt-2 text-sm text-cp-muted">
                    {count} station(s) équipée(s).
                  </p>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <h2 className="font-display mt-16 flex items-center gap-2 text-2xl font-bold">
        <Glasses className="h-8 w-8 text-cp-vr" />
        Réalité virtuelle
      </h2>

      {!data ? (
        <p className="mt-6 text-cp-muted">Chargement…</p>
      ) : vrModels.length === 0 ? (
        <p className="mt-6 text-cp-muted">Aucun casque VR déclaré pour le moment.</p>
      ) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {vrModels.map(([model, count]) => (
            <Card key={model} className="border-cp-vr/20 p-6">
              <h3 className="font-display font-semibold text-cp-vr">{model}</h3>
              <p className="mt-2 text-sm text-cp-muted">{count} station(s).</p>
            </Card>
          ))}
        </div>
      )}

      <h2 className="font-display mt-16 text-2xl font-bold">Stations & jeux disponibles</h2>
      <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {(data?.stations ?? []).slice(0, 9).map((st) => (
          <Card key={st.id} className="p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-muted">
              {st.code}
            </p>
            <h3 className="font-display mt-2 text-lg font-semibold">{st.name}</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {st.tv_size_inches != null ? (
                <span className="rounded-full border border-cp-border bg-cp-bg/60 px-3 py-1 text-xs text-cp-muted">
                  TV {st.tv_size_inches} pouces
                </span>
              ) : null}
              {st.console_model ? (
                <span className="rounded-full border border-cp-border bg-cp-bg/60 px-3 py-1 text-xs text-cp-muted">
                  {st.console_model}
                </span>
              ) : null}
              {st.vr_headset_model ? (
                <span className="rounded-full border border-cp-vr/30 bg-cp-vr/10 px-3 py-1 text-xs text-cp-muted">
                  VR {st.vr_headset_model}
                </span>
              ) : null}
            </div>
            <div className="mt-4">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-cp-muted">
                Jeux
              </p>
              <ul className="mt-2 list-disc pl-5 text-sm text-cp-muted">
                {st.games.slice(0, 4).map((g) => (
                  <li key={g.id}>
                    {g.name} ({g.duration_minutes} min)
                  </li>
                ))}
                {st.games.length === 0 ? (
                  <li>Aucun jeu actif</li>
                ) : null}
              </ul>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
