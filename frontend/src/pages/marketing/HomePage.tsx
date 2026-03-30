import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Headphones,
  MapPin,
  QrCode,
  ShoppingBag,
  Timer,
  Tv,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet } from '../../lib/api'
import { cn } from '../../lib/cn'

type PublicSalle = {
  id: number
  code: string
  name: string
  latitude: number | null
  longitude: number | null
}

const PILIERS = [
  {
    title: 'Location consoles',
    desc: 'PlayStation, Xbox, Nintendo Switch, PC gaming : du casual au compétitif, par créneaux clairs.',
    icon: Tv,
    tone: 'from-cp-cyan/20 to-transparent',
  },
  {
    title: 'Casques VR',
    desc: 'Sessions VR immersives avec matériel entretenu et jeux adaptés à chaque niveau.',
    icon: Headphones,
    tone: 'from-cp-vr/25 to-transparent',
  },
  {
    title: 'Boutique',
    desc: 'Accessoires, jeux et équipements en vente — prolongez l’expérience chez vous.',
    icon: ShoppingBag,
    tone: 'from-cp-amber/20 to-transparent',
  },
  {
    title: 'Carte & salles',
    desc: 'Retrouvez nos espaces sur la carte, horaires et itinéraires en un clic.',
    icon: MapPin,
    tone: 'from-cp-accent/20 to-transparent',
  },
] as const

const ETAPES = [
  {
    step: '1',
    title: 'Choisir une salle',
    text: 'Repérez l’espace le plus proche sur la carte ou la liste des lieux partenaires.',
  },
  {
    step: '2',
    title: 'Scanner le QR',
    text: 'Sur place, scannez le code affiché sur la TV de la station pour ouvrir la page de la session.',
  },
  {
    step: '3',
    title: 'Payer le temps',
    text: 'Sélectionnez une offre (durée + tarif), payez en ligne, la session démarre automatiquement.',
  },
] as const

export function HomePage() {
  const [salles, setSalles] = useState<PublicSalle[] | null>(null)

  useEffect(() => {
    apiGet<{ salles: PublicSalle[] }>('/public/salles')
      .then((d) => setSalles(d.salles))
      .catch(() => setSalles([]))
  }, [])

  return (
    <>
      <section className="relative overflow-hidden">
        <div className="hero-glow pointer-events-none absolute inset-0" />
        <div className="relative mx-auto max-w-6xl px-4 pb-16 pt-12 md:px-6 md:pb-24 md:pt-16">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-cp-accent/30 bg-cp-accent/10 px-3 py-1 text-xs font-medium text-cp-cyan">
            <Timer className="h-3.5 w-3.5" />
            Location · VR · Vente · Temps de jeu
          </p>
          <h1 className="font-display max-w-4xl text-4xl font-extrabold leading-[1.08] tracking-tight md:text-6xl">
            Le gaming,{' '}
            <span className="text-gradient-brand">simple et connecté</span>.
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-cp-muted md:text-xl">
            Un même système pour louer des consoles et des casques VR, vendre du matériel, afficher vos
            salles sur une carte et laisser les clients acheter leur temps de jeu en scannant un QR.
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Link to="/carte">
              <Button className="gap-2">
                Voir les salles
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/jeux">
              <Button variant="secondary" className="gap-2">
                <QrCode className="h-4 w-4" />
                Jeux & offres
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 md:px-6">
        <h2 className="font-display text-center text-2xl font-bold md:text-3xl">
          Tout ce que couvre la plateforme
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-center text-cp-muted">
          Pensé pour les opérateurs multi-salles et le parcours client sur place.
        </p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILIERS.map((p) => (
            <Card
              key={p.title}
              className={cn(
                'relative overflow-hidden border-white/5 p-6 transition hover:border-cp-accent/30',
              )}
            >
              <div
                className={cn(
                  'pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-gradient-to-br opacity-60 blur-2xl',
                  p.tone,
                )}
              />
              <p.icon className="relative h-9 w-9 text-cp-cyan" />
              <h3 className="relative mt-4 font-display text-lg font-semibold">{p.title}</h3>
              <p className="relative mt-2 text-sm leading-relaxed text-cp-muted">{p.desc}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="border-y border-white/[0.06] bg-black/15 py-16 md:py-20">
        <div className="mx-auto max-w-6xl px-4 md:px-6">
          <h2 className="font-display text-center text-2xl font-bold md:text-3xl">
            Côté client : comment ça marche
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {ETAPES.map((e) => (
              <div key={e.step} className="text-center">
                <span className="font-display inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent to-cp-vr text-lg font-bold text-white">
                  {e.step}
                </span>
                <h3 className="mt-4 font-display text-lg font-semibold">{e.title}</h3>
                <p className="mt-2 text-sm text-cp-muted">{e.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 md:px-6">
        <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h2 className="font-display text-2xl font-bold md:text-3xl">Nos espaces partenaires</h2>
            <p className="mt-2 text-cp-muted">Liste live depuis le réseau (données publiques).</p>
          </div>
          <Link to="/carte" className="text-sm font-medium text-cp-cyan hover:underline">
            Ouvrir la carte →
          </Link>
        </div>
        <ul className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(salles ?? []).slice(0, 6).map((s) => (
            <li key={s.id}>
              <a href={`/salle/${encodeURIComponent(s.code)}`}>
                <Card className="p-4 transition hover:border-cp-cyan/40">
                  <p className="font-mono text-xs text-cp-accent">{s.code}</p>
                  <p className="mt-1 font-medium">{s.name}</p>
                  <p className="mt-2 text-xs text-cp-muted">Page publique salle (serveur)</p>
                </Card>
              </a>
            </li>
          ))}
          {salles && salles.length === 0 ? (
            <li className="col-span-full text-sm text-cp-muted">Aucune salle publiée pour l’instant.</li>
          ) : null}
          {!salles ? (
            <li className="col-span-full text-sm text-cp-muted">Chargement des salles…</li>
          ) : null}
        </ul>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 md:px-6">
        <Card className="relative overflow-hidden border-cp-accent/25 bg-gradient-to-br from-cp-accent/10 via-transparent to-cp-vr/10 p-8 md:p-10">
          <h2 className="font-display text-2xl font-bold md:text-3xl">Déjà un compte ?</h2>
          <p className="mt-3 max-w-xl text-cp-muted">
            Accédez à votre espace pour gérer salles, stations, offres et paiements, ou suivre les
            sessions. Un seul point d’entrée pour tous les comptes autorisés.
          </p>
          <Link to="/login" className="mt-6 inline-block">
            <Button>Se connecter</Button>
          </Link>
        </Card>
      </section>
    </>
  )
}
