import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Gamepad2, Headphones, Package, Shirt, Store, CheckCircle2 } from 'lucide-react'
import { Card } from '../../components/Card'
import { apiGet } from '../../lib/api'

type Product = {
  id: number
  name: string
  description: string | null
  price_xof: number
  provider: string
}

const RAYONS = [
  {
    titre: 'Jeux physiques & démat',
    desc: 'Nouveautés et hits : vente au comptoir ou commande en ligne sur cette page.',
    icon: Gamepad2,
  },
  {
    titre: 'Accessoires',
    desc: 'Manettes, batteries, câbles — réassort aligné sur votre parc salons.',
    icon: Headphones,
  },
  {
    titre: 'Goodies & textile',
    desc: 'Licences partenaires, merchandising de salle.',
    icon: Shirt,
  },
  {
    titre: 'Matériel premium',
    desc: 'Casques, volants, périphériques gaming.',
    icon: Package,
  },
]

export function BoutiquePage() {
  const [params] = useSearchParams()
  const commandeOk = params.get('commande') === 'ok'

  const [products, setProducts] = useState<Product[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let c = false
    ;(async () => {
      try {
        const d = await apiGet<{ products: Product[] }>('/public/shop-products')
        if (!c) setProducts(d.products)
      } catch (e) {
        if (!c) setErr(e instanceof Error ? e.message : 'Erreur')
      }
    })()
    return () => {
      c = true
    }
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-amber">Boutique</p>
      <h1 className="font-display mt-2 text-4xl font-extrabold tracking-tight md:text-5xl">
        Vente en <span className="text-gradient-brand">salle</span>
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-cp-muted">
        Commandez des articles depuis le catalogue numérique : paiement en ligne puis retrait ou
        livraison selon vos process (même passerelle PSP que les offres temps de jeu).
      </p>

      {commandeOk ? (
        <Card className="mt-8 flex gap-4 border-emerald-500/30 bg-emerald-500/10 p-4">
          <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-300" aria-hidden />
          <div className="text-sm text-cp-muted">
            <p className="font-semibold text-emerald-100">Merci pour votre commande.</p>
            <p className="mt-1">
              La confirmation paiement peut arriver quelques secondes après le retour PSP. Conservez
              l’email de reçu si vous l’avez saisi.
            </p>
          </div>
        </Card>
      ) : null}

      <div className="mt-6">
        <Link
          to="/boutique/commande"
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cp-accent to-cp-vr px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cp-accent/25 transition hover:brightness-110"
        >
          <Store className="h-4 w-4" />
          Passer commande
        </Link>
      </div>

      {err ? <p className="mt-8 text-rose-300">{err}</p> : null}

      <h2 className="font-display mt-14 text-xl font-bold">Catalogue en ligne</h2>
      {!products ? (
        <p className="mt-4 text-cp-muted">Chargement du catalogue…</p>
      ) : products.length === 0 ? (
        <p className="mt-4 text-cp-muted">
          Aucun produit publié pour le moment. Les administrateurs plateforme ajoutent les articles
          dans <strong className="text-cp-text">Produits boutique</strong> (admin).
        </p>
      ) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <Card key={p.id} className="flex flex-col border-cp-amber/15 p-6">
              <p className="text-xs font-mono text-cp-muted">#{p.id}</p>
              <h3 className="font-display mt-1 text-lg font-semibold">{p.name}</h3>
              {p.description ? (
                <p className="mt-2 flex-1 text-sm text-cp-muted">{p.description}</p>
              ) : null}
              <p className="mt-4 text-lg font-bold text-cp-amber">{p.price_xof} XOF</p>
              <Link
                to={`/boutique/commande?produit=${p.id}`}
                className="mt-4 inline-block text-sm font-medium text-cp-teal hover:underline"
              >
                Commander →
              </Link>
            </Card>
          ))}
        </div>
      )}

      <div className="mt-16 grid gap-4 sm:grid-cols-2">
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
          Logistique (stock, retrait, transport) : à paramétrer côté exploitation ; le tunnel
          e-commerce (création de commande + paiement) est opérationnel côté ControlPlay.
        </p>
      </Card>
    </div>
  )
}
