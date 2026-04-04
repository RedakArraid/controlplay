import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Cpu, Disc, Glasses, MonitorPlay } from 'lucide-react'
import { Card } from '../../components/Card'
import { apiGet } from '../../lib/api'

type PartnerStation = {
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

type PartnerResp = {
  stations: PartnerStation[]
}
type RentalConsole = {
  id: number
  code: string
  name: string
  tv_size_inches: number | null
  console_model: string | null
  controller_count: number | null
  notes: string | null
  games: Array<{ id: number; name: string; platform: string | null }>
}
type RentalResp = { consoles: RentalConsole[] }

export function LocationPage() {
  const [data, setData] = useState<PartnerResp | null>(null)
  const [rental, setRental] = useState<RentalResp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      apiGet<PartnerResp>('/public/stations'),
      apiGet<RentalResp>('/public/rental-consoles'),
    ])
      .then(([partnerRes, rentalRes]) => {
        setData(partnerRes)
        setRental(rentalRes)
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [])

  const rentalConsoles = useMemo(() => rental?.consoles ?? [], [rental])
  const gameStations = useMemo(() => data?.stations ?? [], [data])

  const consoleModels = (list: Array<{ console_model: string | null }>) => {
    const m = new Map<string, number>()
    for (const st of list) {
      if (!st.console_model) continue
      m.set(st.console_model, (m.get(st.console_model) ?? 0) + 1)
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }

  const vrModels = (list: Array<{ vr_headset_model?: string | null }>) => {
    const m = new Map<string, number>()
    for (const st of list) {
      const vr = (st as { vr_headset_model?: string | null }).vr_headset_model
      if (!vr) continue
      m.set(vr, (m.get(vr) ?? 0) + 1)
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }

  const consoleRental = useMemo(() => consoleModels(rentalConsoles), [rentalConsoles])
  const consolePartner = useMemo(() => consoleModels(gameStations), [gameStations])
  const vrPartner = useMemo(() => vrModels(gameStations), [gameStations])

  const ModelCard = ({
    model,
    count,
    variant,
  }: {
    model: string
    count: number
    variant: 'rental' | 'partner'
  }) => {
    const modelLower = model.toLowerCase()
    const Icon = modelLower.includes('playstation')
      ? Disc
      : modelLower.includes('switch')
        ? Cpu
        : MonitorPlay
    return (
      <Card
        key={model}
        className={
          variant === 'rental'
            ? 'flex gap-4 border-cp-accent/20 p-6'
            : 'flex gap-4 p-6'
        }
      >
        <span
          className={
            variant === 'rental'
              ? 'flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cp-accent/15 text-cp-accent'
              : 'flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cp-cyan/15 text-cp-cyan'
          }
        >
          <Icon className="h-6 w-6" />
        </span>
        <div>
          <h3 className="font-display text-lg font-semibold">{model}</h3>
          <p className="mt-2 text-sm text-cp-muted">{count} poste(s).</p>
        </div>
      </Card>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-accent">Location</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Consoles & <span className="text-gradient-brand">casques VR</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        Nous distinguons le <strong>parc location ControlPlay</strong> (matériel loué, forfaits dédiés)
        des <strong>postes en salles partenaires</strong> (achat de temps de jeu sur place via QR).
      </p>

      <Card className="mt-8 border-cp-accent/25 bg-cp-accent/5 p-6">
        <h2 className="font-display text-lg font-semibold text-cp-text">Réserver un forfait location</h2>
        <p className="mt-2 max-w-xl text-sm text-cp-muted">
          Tarifs et durées des forfaits « location console » — paiement en ligne selon la configuration PSP.
        </p>
        <a
          href="/rental"
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-cp-accent px-4 py-2.5 text-sm font-semibold text-cp-bg shadow-lg shadow-cp-accent/20 transition hover:opacity-90"
        >
          Voir les forfaits & payer
        </a>
      </Card>

      {err ? <p className="mt-6 text-rose-300">{err}</p> : null}

      <h2 className="font-display mt-16 text-2xl font-bold text-cp-accent">
        Parc location ControlPlay
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-cp-muted">
        Postes déclarés comme « location » dans l’admin : TV, console, manettes, jeux décrits sur le
        matériel (sans lien obligatoire avec les offres temps de jeu des salles partenaires).
      </p>

      {!data ? (
        <p className="mt-8 text-cp-muted">Chargement…</p>
      ) : rentalConsoles.length === 0 ? (
        <p className="mt-8 text-cp-muted">
          Aucun poste location publié pour le moment (admin : stations, type « location ControlPlay »).
        </p>
      ) : (
        <>
          <h3 className="font-display mt-10 text-lg font-semibold">Familles de consoles (location)</h3>
          {consoleRental.length === 0 ? (
            <p className="mt-4 text-cp-muted">Aucun modèle de console renseigné.</p>
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {consoleRental.map(([model, count]) => (
                <ModelCard key={model} model={model} count={count} variant="rental" />
              ))}
            </div>
          )}
          <h3 className="font-display mt-10 text-lg font-semibold">Détail des postes</h3>
          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {rentalConsoles.map((st) => (
              <Card key={st.id} className="border-cp-accent/15 p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-accent">Location</p>
                <p className="text-xs font-mono text-cp-muted">{st.code}</p>
                <h4 className="font-display mt-2 text-lg font-semibold">{st.name}</h4>
                <div className="mt-3 flex flex-wrap gap-2">
                  {st.tv_size_inches != null ? (
                    <span className="rounded-full border border-cp-border bg-cp-bg/60 px-3 py-1 text-xs text-cp-muted">
                      TV {st.tv_size_inches}&quot;
                    </span>
                  ) : null}
                  {st.console_model ? (
                    <span className="rounded-full border border-cp-border bg-cp-bg/60 px-3 py-1 text-xs text-cp-muted">
                      {st.console_model}
                    </span>
                  ) : null}
                  {st.controller_count != null && st.controller_count > 0 ? (
                    <span className="rounded-full border border-cp-border bg-cp-bg/60 px-3 py-1 text-xs text-cp-muted">
                      {st.controller_count} manette(s)
                    </span>
                  ) : null}
                </div>
                {st.notes ? (
                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-cp-muted">
                      Notes matériel
                    </p>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-cp-muted">{st.notes}</p>
                  </div>
                ) : null}
                {st.games && st.games.length ? (
                  <div className="mt-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-cp-muted">
                      Jeux déclarés
                    </p>
                    <ul className="mt-1 list-disc pl-4 text-xs text-cp-muted">
                      {st.games.slice(0, 6).map((g) => (
                        <li key={g.id}>{g.platform ? `${g.name} (${g.platform})` : g.name}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </Card>
            ))}
          </div>
        </>
      )}

      <h2 className="font-display mt-20 text-2xl font-bold text-cp-cyan">
        Salles partenaires — temps de jeu
      </h2>
      <p className="mt-2 max-w-2xl text-sm text-cp-muted">
        Ces postes ne sont pas tous gérés comme le parc ControlPlay : les offres (durée / prix) sont
        celles de la salle. Achat sur place via QR <code className="text-cp-accent">/s/…</code>.
      </p>

      {!data ? null : gameStations.length === 0 ? (
        <p className="mt-8 text-cp-muted">Aucune station « salle de jeu » publiée.</p>
      ) : (
        <>
          <h3 className="font-display mt-10 text-lg font-semibold">Familles de consoles (partenaires)</h3>
          {consolePartner.length === 0 ? (
            <p className="mt-4 text-cp-muted">Aucun modèle renseigné.</p>
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {consolePartner.map(([model, count]) => (
                <ModelCard key={model} model={model} count={count} variant="partner" />
              ))}
            </div>
          )}
          <h3 className="font-display mt-10 flex items-center gap-2 text-lg font-semibold">
            <Glasses className="h-6 w-6 text-cp-vr" />
            VR (partenaires)
          </h3>
          {vrPartner.length === 0 ? (
            <p className="mt-4 text-cp-muted">Aucun casque VR déclaré.</p>
          ) : (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {vrPartner.map(([model, count]) => (
                <Card key={model} className="border-cp-vr/20 p-6">
                  <h4 className="font-display font-semibold text-cp-vr">{model}</h4>
                  <p className="mt-2 text-sm text-cp-muted">{count} station(s).</p>
                </Card>
              ))}
            </div>
          )}
          <h3 className="font-display mt-10 text-lg font-semibold">Stations & offres temps de jeu</h3>
          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {gameStations.slice(0, 12).map((st) => (
              <Card key={st.id} className="p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-muted">
                  Partenaire
                </p>
                <p className="text-xs font-mono text-cp-muted">{st.code}</p>
                <h4 className="font-display mt-2 text-lg font-semibold">{st.name}</h4>
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
                    Offres (temps de jeu)
                  </p>
                  <ul className="mt-2 list-disc pl-5 text-sm text-cp-muted">
                    {st.games.slice(0, 4).map((g) => (
                      <li key={g.id}>
                        {g.name} ({g.duration_minutes} min)
                      </li>
                    ))}
                    {st.games.length === 0 ? <li>Aucune offre active</li> : null}
                  </ul>
                </div>
                <Link
                  to={`/s/${encodeURIComponent(st.code)}`}
                  className="mt-4 inline-block text-sm font-medium text-cp-teal hover:underline"
                >
                  Ouvrir la page station (QR) →
                </Link>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
