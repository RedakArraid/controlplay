import { Gamepad2, Headphones, Package, Shirt } from 'lucide-react'
import { Card } from '../../components/Card'

const RAYONS = [
  {
    titre: 'Jeux physiques & démat',
    desc: 'Nouveautés et hits : vente au comptoir ou précommande liée à votre stock.',
    icon: Gamepad2,
  },
  {
    titre: 'Accessoires',
    desc: 'Manettes, batteries, câbles, protections — tout ce qui évite une session interrompue.',
    icon: Headphones,
  },
  {
    titre: 'Goodies & textile',
    desc: 'Licences partenaires, merchandising de salle, packs cadeaux.',
    icon: Shirt,
  },
  {
    titre: 'Matériel premium',
    desc: 'Casques, volants, sticks arcade : upsell pour les joueurs réguliers.',
    icon: Package,
  },
]

export function BoutiquePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-amber">Boutique</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Vente en <span className="text-gradient-brand">salle</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        ControlPlay est d’abord centré sur la location et le temps de jeu ; la partie « boutique »
        complète l’expérience : même marque, même lieu, même relation client. Les modules e-commerce
        détaillés peuvent se brancher sur votre flux (caisse, stock, livraison).
      </p>

      <div className="mt-12 grid gap-4 sm:grid-cols-2">
        {RAYONS.map((r) => (
          <Card key={r.titre} className="flex gap-4 border-cp-amber/15 p-6">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cp-amber/15 text-cp-amber">
              <r.icon className="h-6 w-6" />
            </span>
            <div>
              <h2 className="font-display text-lg font-semibold">{r.titre}</h2>
              <p className="mt-2 text-sm text-cp-muted">{r.desc}</p>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-12 border-dashed border-cp-border/80 p-6 text-center">
        <p className="text-sm text-cp-muted">
          Catalogue produit, panier et paiement en ligne : à intégrer selon votre stack (tunnel dédié,
          lien vers marketplace, ou module interne). La structure du site est prête pour accueillir ces
          parcours.
        </p>
      </Card>
    </div>
  )
}
