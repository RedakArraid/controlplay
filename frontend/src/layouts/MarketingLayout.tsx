import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Gamepad2, Menu, X } from 'lucide-react'
import { useState } from 'react'
import { cn } from '../lib/cn'

const NAV = [
  { to: '/', label: 'Accueil', end: true },
  { to: '/location', label: 'Location' },
  { to: '/boutique', label: 'Boutique' },
  { to: '/carte', label: 'Carte des salles' },
  { to: '/jeux', label: 'Jeux & temps de jeu' },
] as const

export function MarketingLayout() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()

  return (
    <div className="relative min-h-screen">
      <div className="pointer-events-none fixed inset-0 grid-bg opacity-50" />
      <div className="pointer-events-none fixed inset-0 noise-overlay" />

      <header className="sticky top-0 z-50 border-b border-white/[0.06] bg-cp-bg/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 md:px-6">
          <Link
            to="/"
            className="flex shrink-0 items-center gap-2.5"
            onClick={() => setOpen(false)}
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent via-cp-vr to-cp-cyan text-white shadow-lg shadow-cp-accent/25">
              <Gamepad2 className="h-5 w-5" aria-hidden />
            </span>
            <div className="leading-tight">
              <span className="font-display text-lg font-bold tracking-tight">ControlPlay</span>
              <p className="hidden text-[10px] font-medium uppercase tracking-[0.2em] text-cp-muted sm:block">
                Console · VR · Salles
              </p>
            </div>
          </Link>

          <nav className="hidden items-center gap-1 lg:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={'end' in item ? item.end : false}
                className={({ isActive }) =>
                  cn(
                    'rounded-xl px-3 py-2 text-sm font-medium transition',
                    isActive
                      ? 'bg-white/10 text-cp-text'
                      : 'text-cp-muted hover:bg-white/5 hover:text-cp-text',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Link
              to="/login"
              className="inline-flex rounded-xl bg-gradient-to-r from-cp-accent to-cp-vr px-4 py-2 text-sm font-semibold text-white shadow-md shadow-cp-accent/20 hover:brightness-110"
            >
              Se connecter
            </Link>
            <button
              type="button"
              className="rounded-lg p-2 text-cp-muted lg:hidden"
              aria-expanded={open}
              aria-label={open ? 'Fermer le menu' : 'Ouvrir le menu'}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>

        {open ? (
          <div className="border-t border-white/5 bg-cp-bg/95 px-4 py-4 lg:hidden">
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={'end' in item ? item.end : false}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      'rounded-xl px-3 py-3 text-base font-medium',
                      isActive ? 'bg-white/10 text-cp-text' : 'text-cp-muted',
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
              <Link
                to="/login"
                className="mt-2 rounded-xl bg-gradient-to-r from-cp-accent to-cp-vr px-3 py-3 text-center text-sm font-semibold text-white shadow-md shadow-cp-accent/20"
                onClick={() => setOpen(false)}
              >
                Se connecter
              </Link>
            </nav>
          </div>
        ) : null}
      </header>

      <main className="relative z-10">
        <Outlet key={pathname} />
      </main>

      <footer className="relative z-10 mt-20 border-t border-white/[0.06] bg-black/20">
        <div className="mx-auto max-w-6xl px-4 py-14 md:px-6">
          <div className="grid gap-10 md:grid-cols-3">
            <div>
              <p className="font-display text-lg font-bold">ControlPlay</p>
              <p className="mt-2 max-w-xs text-sm text-cp-muted">
                Réseau de salles de jeu : location de consoles et casques VR, vente, et achat de temps
                de jeu sur place via QR code.
              </p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-cp-muted">Parcourir</p>
              <ul className="mt-3 space-y-2 text-sm">
                {NAV.map((item) => (
                  <li key={item.to}>
                    <Link className="text-cp-text/80 hover:text-cp-cyan" to={item.to}>
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-cp-muted">Client</p>
              <p className="mt-3 text-sm text-cp-muted">
                Pour jouer : rendez-vous en salle, scannez le QR sur l’écran de la station, choisissez
                votre durée et payez en ligne. Pas de compte obligatoire.
              </p>
            </div>
          </div>
          <p className="mt-12 border-t border-white/5 pt-8 text-center text-xs text-cp-muted">
            © {new Date().getFullYear()} ControlPlay — Système de gestion salles & stations.
          </p>
        </div>
      </footer>
    </div>
  )
}
