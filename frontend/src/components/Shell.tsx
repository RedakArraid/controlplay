import type { CSSProperties, ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  LogOut,
  Menu,
  X,
  LayoutDashboard,
  Store,
  Tag,
  Monitor,
  PlayCircle,
  MessageSquare,
  Users,
  Settings,
  Gamepad2,
  Package,
  Disc3,
  ShoppingBag,
  ShoppingCart,
  Building2,
  ChevronRight,
  Globe,
  UserPlus,
  Zap,
} from 'lucide-react'
import { useState } from 'react'
import type { NavItem } from '../types'
import { cn } from '../lib/cn'

const NAV_ICONS: Record<string, React.ElementType> = {
  'Tableau de bord': LayoutDashboard,
  'Dashboard stations': Monitor,
  Salles: Building2,
  Offres: Tag,
  Stations: Gamepad2,
  Sessions: PlayCircle,
  Feedback: MessageSquare,
  'Mes utilisateurs': UserPlus,
  'Session manuelle': Zap,
  'Forfaits location': Package,
  'Consoles location': Disc3,
  'Jeux location': ShoppingBag,
  'Produits boutique': ShoppingCart,
  'Utilisateurs globaux': Users,
  'Providers PSP': Settings,
  'Super admin': Globe,
  'Équipe ControlPlay': Globe,
  Boutique: Store,
}

export function AppShell({
  zone,
  title,
  nav,
  userLabel,
  children,
}: {
  zone: 'admin' | 'super'
  title: string
  nav: NavItem[]
  userLabel: string
  children?: ReactNode
}) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="relative min-h-screen"
      data-zone={zone}
      style={{ '--cp-zone-accent': 'var(--color-cp-accent)' } as CSSProperties}
    >
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />
      <div
        className="pointer-events-none absolute -left-32 top-0 h-96 w-96 rounded-full blur-3xl"
        style={{ background: 'var(--cp-zone-glow, oklch(0.55 0.12 250 / 0.2))' }}
      />

      <div className="relative z-10 flex min-h-screen">
        {/* ── Sidebar ── */}
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-40 w-72 border-r border-white/10 bg-cp-bg/90 backdrop-blur-xl transition-transform duration-300 md:static md:translate-x-0',
            open ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          {/* Brand */}
          <div className="flex h-16 items-center justify-between border-b border-white/5 px-4">
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-xl text-sm font-bold text-white shadow-lg',
                  zone === 'super'
                    ? 'bg-gradient-to-br from-sky-400 to-indigo-600'
                    : 'bg-gradient-to-br from-cp-accent to-cp-vr',
                )}
              >
                CP
              </span>
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-cp-muted">
                  {title}
                </p>
                <p className="text-sm font-semibold">{userLabel}</p>
              </div>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-cp-muted transition hover:bg-white/5 md:hidden"
              onClick={() => setOpen(false)}
              aria-label="Fermer le menu"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Nav */}
          <nav className="flex flex-col gap-0.5 p-3">
            {nav.map((item) => {
              const Icon = NAV_ICONS[item.label] ?? ChevronRight
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/admin' || item.to === '/super-admin'}
                  onClick={() => setOpen(false)}
                  className={({ isActive }) =>
                    cn(
                      'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-150',
                      isActive
                        ? 'bg-white/10 font-semibold text-cp-text shadow-inner'
                        : 'text-cp-muted hover:bg-white/5 hover:text-cp-text',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className={cn(
                          'h-4 w-4 shrink-0 transition-colors',
                          isActive
                            ? 'text-cp-cyan'
                            : 'text-cp-muted group-hover:text-cp-text',
                        )}
                      />
                      <span className="flex-1">{item.label}</span>
                      {isActive && (
                        <span className="h-1.5 w-1.5 rounded-full bg-cp-cyan" />
                      )}
                    </>
                  )}
                </NavLink>
              )
            })}
          </nav>

          {/* Déconnexion */}
          <div className="absolute bottom-0 left-0 right-0 border-t border-white/5 p-3">
            <a
              href="/logout"
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-cp-muted transition hover:bg-white/5 hover:text-cp-danger"
            >
              <LogOut className="h-4 w-4" />
              Déconnexion
            </a>
          </div>
        </aside>

        {/* Overlay mobile */}
        {open && (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
            aria-label="Fermer"
            onClick={() => setOpen(false)}
          />
        )}

        {/* Main content */}
        <div className="flex min-h-screen flex-1 flex-col">
          {/* Mobile topbar */}
          <header className="flex h-16 items-center gap-3 border-b border-white/5 bg-cp-bg/40 px-4 backdrop-blur md:hidden">
            <button
              type="button"
              className="rounded-lg p-2 text-cp-muted transition hover:bg-white/5"
              onClick={() => setOpen(true)}
              aria-label="Ouvrir le menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="font-semibold">{title}</span>
          </header>

          <div className="flex-1 overflow-auto p-4 md:p-8 lg:p-10">
            {children ?? <Outlet />}
          </div>
        </div>
      </div>
    </div>
  )
}
