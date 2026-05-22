import { type FormEvent, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { Select } from '../../components/ui/Select'
import { Input } from '../../components/ui/Input'
import { apiGet, postFormNavigate } from '../../lib/api'

type Plan = {
  id: number
  name: string
  description: string | null
  duration_label: string
  price_xof: number
  provider: string
  rental_console_id: number | null
}

type ConsolePick = { id: number; code: string; name: string }

type CatalogResp = { plans: Plan[]; consoles: ConsolePick[] }

export function LocationReservationPage() {
  const [catalog, setCatalog] = useState<CatalogResp | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const [planId, setPlanId] = useState('')
  const [consoleCode, setConsoleCode] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [connect, setConnect] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let c = false
    ;(async () => {
      try {
        const d = await apiGet<CatalogResp>('/public/rental-catalog')
        if (c) return
        setCatalog(d)
        if (d.plans.length) setPlanId(String(d.plans[0].id))
        if (d.consoles.length) setConsoleCode(d.consoles[0].code)
      } catch (e) {
        if (!c) setErr(e instanceof Error ? e.message : 'Erreur catalogue')
      }
    })()
    return () => {
      c = true
    }
  }, [])

  const validPlanConsole = () => {
    if (!catalog || !planId || !consoleCode) return true
    const pid = Number(planId)
    const plan = catalog.plans.find((p) => p.id === pid)
    const cons = catalog.consoles.find((x) => x.code === consoleCode)
    if (!plan || !cons) return false
    if (
      plan.rental_console_id != null &&
      plan.rental_console_id !== cons.id
    )
      return false
    return true
  }

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setErr(null)
    if (!validPlanConsole()) {
      setErr("Ce forfait n'est pas disponible pour la console sélectionnée.")
      return
    }
    if (connect && !phone.trim()) {
      setErr('Numéro de téléphone obligatoire si « lier un compte ».')
      return
    }
    try {
      setSaving(true)
      await postFormNavigate('/rental/checkout', {
        rental_plan_id: planId,
        console_code: consoleCode,
        email: email.trim(),
        phone: phone.trim(),
        connect: connect ? '1' : '0',
      })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Paiement impossible')
    } finally {
      setSaving(false)
    }
  }

  const plans = catalog?.plans ?? []
  const consoles = catalog?.consoles ?? []

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-accent">
        Réservation
      </p>
      <h1 className="font-display mt-2 text-3xl font-extrabold tracking-tight md:text-4xl">
        Location <span className="text-gradient-brand">console</span>
      </h1>
      <p className="mt-4 text-sm text-cp-muted">
        Paiement en ligne (Paystack / CinetPay selon configuration). Même tunnel que la page
        classique <code className="text-cp-accent">/rental</code>, avec l’interface ControlPlay.
      </p>

      <div className="mt-6 flex flex-wrap gap-3 text-sm">
        <Link to="/location" className="text-cp-teal hover:underline">
          ← Vitrine location
        </Link>
        <span className="text-cp-muted">·</span>
        <a href="/rental" className="text-cp-muted hover:text-cp-text">
          Version HTML simple
        </a>
      </div>

      {!catalog && !err ? (
        <p className="mt-10 flex items-center gap-2 text-cp-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Chargement du catalogue…
        </p>
      ) : null}

      {err ? <p className="mt-8 text-rose-300">{err}</p> : null}

      {catalog && plans.length === 0 ? (
        <p className="mt-10 text-cp-muted">
          Aucun forfait actif. Connectez-vous en admin plateforme pour créer des forfaits location.
        </p>
      ) : null}

      {catalog && plans.length > 0 && consoles.length === 0 ? (
        <p className="mt-10 text-cp-muted">
          Aucune console de point de retrait active. Déclarez au moins une console dans{' '}
          <strong className="text-cp-text">Consoles location</strong> (admin).
        </p>
      ) : null}

      {catalog && plans.length > 0 && consoles.length > 0 ? (
        <Card className="mt-10 border-white/10 p-6 md:p-8">
          <form className="space-y-6" onSubmit={submit}>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-cp-muted">Forfait</label>
              <Select
                value={planId}
                onChange={(e) => setPlanId(e.target.value)}
                disabled={saving}
                required
              >
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {p.price_xof} XOF ({p.duration_label})
                  </option>
                ))}
              </Select>
              {plans.find((p) => p.id === Number(planId))?.description ? (
                <p className="text-xs text-cp-muted">
                  {plans.find((p) => p.id === Number(planId))?.description}
                </p>
              ) : null}
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-cp-muted">
                Console / point de retrait
              </label>
              <Select
                value={consoleCode}
                onChange={(e) => setConsoleCode(e.target.value)}
                disabled={saving}
                required
              >
                {consoles.map((c) => (
                  <option key={c.id} value={c.code}>
                    {c.code} — {c.name}
                  </option>
                ))}
              </Select>
              {!validPlanConsole() ? (
                <p className="text-xs font-medium text-rose-300">
                  Ce forfait est réservé à une console précise (voir admin).
                </p>
              ) : null}
            </div>

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={connect}
                onChange={(e) => setConnect(e.target.checked)}
                className="mt-1"
              />
              <span className="text-cp-muted">
                Lier un compte téléphone pour le suivi (le numéro devient alors obligatoire).
              </span>
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-cp-muted">
                  Email {connect ? '' : '(optionnel)'}
                </label>
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  disabled={saving}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-cp-muted">
                  Téléphone {connect ? '(obligatoire)' : '(optionnel)'}
                </label>
                <Input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  autoComplete="tel"
                  disabled={saving}
                  required={connect}
                />
              </div>
            </div>

            <Button type="submit" disabled={saving || !validPlanConsole()} className="w-full sm:w-auto">
              {saving ? 'Redirection…' : 'Payer la location'}
            </Button>
          </form>
        </Card>
      ) : null}
    </div>
  )
}
