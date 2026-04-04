import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Gamepad2, Lock } from 'lucide-react'
import { Card } from '../components/Card'
import { Button } from '../components/ui/Button'
import { apiGet, apiPostJson } from '../lib/api'
import type { AuthMe } from '../types'

export function Login() {
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const next = search.get('next') || '/admin'
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    apiGet<AuthMe>('/auth/me')
      .then(() => {
        navigate(next.startsWith('/') ? next : '/admin', { replace: true })
      })
      .catch(() => {
        /* non connecté */
      })
  }, [navigate, next])

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiPostJson<{ redirect: string }>('/auth/login', {
        identifier,
        password,
        next,
      })
      window.location.assign(res.redirect)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Échec de la connexion')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen">
      <div className="pointer-events-none fixed inset-0 grid-bg opacity-50" />
      <div className="pointer-events-none fixed inset-0 noise-overlay" />
      <header className="relative z-10 border-b border-white/[0.06] bg-cp-bg/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 md:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent via-cp-vr to-cp-cyan text-white shadow-lg">
              <Gamepad2 className="h-5 w-5" aria-hidden />
            </span>
            <span className="font-display text-lg font-bold tracking-tight">ControlPlay</span>
          </Link>
          <Link
            to="/"
            className="text-sm font-medium text-cp-muted transition hover:text-cp-text"
          >
            ← Accueil
          </Link>
        </div>
      </header>
      <div className="relative z-10 mx-auto max-w-md px-4 py-14 md:py-20">
        <div className="mb-8 text-center">
          <h1 className="font-display text-3xl font-extrabold tracking-tight">Connexion</h1>
          <p className="mt-2 text-sm text-cp-muted">
            Saisissez l’email ou le téléphone et le mot de passe liés à votre compte.
          </p>
        </div>
        <Card className="p-8">
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="login-identifier"
                className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-cp-muted"
              >
                Email ou téléphone
              </label>
              <input
                id="login-identifier"
                name="identifier"
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-4 py-3 text-sm text-cp-text outline-none transition focus:border-cp-accent/50"
                required
              />
            </div>
            <div>
              <label
                htmlFor="login-password"
                className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-cp-muted"
              >
                Mot de passe
              </label>
              <input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-4 py-3 text-sm text-cp-text outline-none transition focus:border-cp-accent/50"
                required
              />
            </div>
            <input type="hidden" name="next" value={next} readOnly />
            {error ? (
              <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                {error}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={loading}>
              <Lock className="h-4 w-4" />
              {loading ? 'Connexion…' : 'Se connecter'}
            </Button>
          </form>
          <p className="mt-6 text-center text-xs text-cp-muted">
            Pour acheter du temps de jeu, rendez-vous en salle et scannez le QR sur l’écran de la station.
          </p>
        </Card>
      </div>
    </div>
  )
}
