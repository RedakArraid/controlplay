import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, Trophy } from 'lucide-react'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet } from '../../lib/api'

type Jeu = {
  id: number
  name: string
  duration_minutes: number
  price_xof: number
  provider: string
  attached: boolean
}

export function JeuxPage() {
  const [jeux, setJeux] = useState<Jeu[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const d = await apiGet<{ jeux: Jeu[] }>('/public/jeux')
        setJeux(d.jeux)
      } catch (e) {
        setErr(e instanceof Error ? e.message : 'Erreur')
      }
    })()
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-vr">Catalogue</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Jeux & <span className="text-gradient-brand">offres temps de jeu</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        Les <strong>offres</strong> (durée + prix en XOF) sont configurées dans l’admin et proposées
        au client après scan du QR de la station.
      </p>

      {err ? <p className="mt-8 text-rose-300">{err}</p> : null}

      <div className="mt-10">
        {!jeux ? (
          <p className="text-cp-muted">Chargement du catalogue…</p>
        ) : jeux.length === 0 ? (
          <p className="text-cp-muted">Aucune offre active pour le moment.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {jeux.map((j) => (
              <Card key={j.id} className="p-5">
                <h2 className="font-display font-semibold">{j.name}</h2>
                <p className="mt-2 text-sm text-cp-muted">
                  {j.duration_minutes} min · {j.price_xof} XOF
                </p>
                <p className="mt-1 text-xs text-cp-muted">Provider: {j.provider}</p>
                <p
                  className={
                    'mt-3 text-xs font-semibold ' +
                    (j.attached ? 'text-cp-teal' : 'text-cp-muted')
                  }
                >
                  {j.attached ? 'Disponible en salle' : 'Template non attaché'}
                </p>
              </Card>
            ))}
          </div>
        )}
      </div>

      <div className="mt-12 grid gap-6 md:grid-cols-2">
        <Card className="border-cp-accent/25 p-6">
          <Trophy className="h-8 w-8 text-cp-amber" />
          <h2 className="font-display mt-4 text-lg font-bold">Acheter du temps</h2>
          <p className="mt-2 text-sm text-cp-muted">
            Sur place, ouvrez la page de la station (QR sur la TV), choisissez une offre, payez avec
            Paystack ou CinetPay selon la configuration du lieu. Cet achat ne passe pas par l’écran de
            connexion ci-dessus.
          </p>
        </Card>
        <Card className="border-cp-cyan/25 p-6">
          <Sparkles className="h-8 w-8 text-cp-cyan" />
          <h2 className="font-display mt-4 text-lg font-bold">Personnaliser le catalogue</h2>
          <p className="mt-2 text-sm text-cp-muted">
            Pour afficher une liste de jeux synchronisée avec votre stock ou vos licences, une future
            extension API pourra alimenter cette page automatiquement. Aujourd’hui, elle sert de vitrine
            pédagogique pour vos clients.
          </p>
        </Card>
      </div>

      <div className="mt-12 text-center">
        <Link to="/carte">
          <Button variant="secondary">Trouver une salle</Button>
        </Link>
      </div>
    </div>
  )
}
