import type { CSSProperties, ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { LogOut, Menu, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import type { NavItem } from '../types'
import { cn } from '../lib/cn'

export function PublicShell({
  children,
  variant = 'home',
}: {
  children: React.ReactNode
  variant?: 'home' | 'login'
}) {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-40" />
      <header className="relative z-10 border-b border-white/5 bg-cp-bg/40 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 md:px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cp-accent to-cp-teal text-cp-bg shadow-lg">
              <Sparkles className="h-5 w-5" aria-hidden />
            </span>
            <span>ControlPlay</span>
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            {variant === 'home' ? (
              <Link
                to="/login"
                className="rounded-lg px-3 py-2 text-cp-muted transition hover:bg-white/5 hover:text-cp-text"
              >
                Se connecter
              </Link>
            ) : (
              <Link
                to="/"
                className="rounded-lg px-3 py-2 text-cp-muted transition hover:bg-white/5 hover:text-cp-text"
              >
                Accueil
              </Link>
            )}
          </nav>
        </div>
      </header>
      <main className="relative z-10 mx-auto max-w-6xl px-4 py-10 md:px-6">
        {children}
      </main>
    </div>
  )
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
      style={
        {
          '--cp-zone-accent': 'var(--color-cp-accent)',
        } as CSSProperties
      }
    >
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />
      <div
        className="pointer-events-none absolute -left-32 top-0 h-96 w-96 rounded-full blur-3xl"
        style={{
          background: 'var(--cp-zone-glow, oklch(0.55 0.12 250 / 0.2))',
        }}
      />
      <div className="relative z-10 flex min-h-screen">
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-40 w-72 border-r border-white/10 bg-cp-bg/80 backdrop-blur-xl transition-transform md:static md:translate-x-0',
            open ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="flex h-16 items-center justify-between border-b border-white/5 px-4">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-xl text-sm font-bold text-cp-bg shadow-lg',
                  zone === 'super'
                    ? 'bg-gradient-to-br from-sky-400 to-indigo-600'
                    : 'bg-gradient-to-br from-cp-accent2 to-amber-600',
                )}
              >
                CP
              </span>
              <div>
                <p className="text-xs text-cp-muted">{title}</p>
                <p className="text-sm font-semibold">{userLabel}</p>
              </div>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-cp-muted md:hidden"
              onClick={() => setOpen(false)}
              aria-label="Fermer le menu"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav className="flex flex-col gap-1 p-3">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/admin' || item.to === '/super-admin'}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'rounded-xl px-3 py-2.5 text-sm transition',
                    isActive
                      ? 'bg-white/10 font-medium text-cp-text shadow-inner'
                      : 'text-cp-muted hover:bg-white/5 hover:text-cp-text',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="absolute bottom-0 left-0 right-0 border-t border-white/5 p-3">
            <a
              href="/logout"
              className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm text-cp-muted transition hover:bg-white/5 hover:text-cp-text"
            >
              <LogOut className="h-4 w-4" />
              Déconnexion
            </a>
          </div>
        </aside>
        {open ? (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/50 md:hidden"
            aria-label="Fermer"
            onClick={() => setOpen(false)}
          />
        ) : null}
        <div className="flex min-h-screen flex-1 flex-col md:pl-0">
          <header className="flex h-16 items-center gap-3 border-b border-white/5 bg-cp-bg/40 px-4 backdrop-blur md:hidden">
            <button
              type="button"
              className="rounded-lg p-2 text-cp-muted"
              onClick={() => setOpen(true)}
              aria-label="Ouvrir le menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="font-medium">{title}</span>
          </header>
          <div className="flex-1 overflow-auto p-4 md:p-8 lg:p-10">
            {children ?? <Outlet />}
          </div>
        </div>
      </div>
    </div>
  )
}
