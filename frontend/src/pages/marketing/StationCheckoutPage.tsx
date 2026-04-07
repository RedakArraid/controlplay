import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, postFormNavigate } from '../../lib/api'
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Gamepad2,
  Headphones,
  Joystick,
  Monitor,
  Phone,
  Star,
  Timer,
  Tv,
  Zap,
  Send,
} from 'lucide-react'

type StationOffer = {
  id: number
  name: string
  duration_minutes: number
  price_xof: number
  provider: string
}

type StationDetail = {
  station: {
    id: number
    code: string
    name: string
    salle_id: number | null
    composition: string[]
    has_active_session: boolean
    offers: StationOffer[]
    bundled_games?: string
    controller_count?: number
  }
}

type FeedbackForm = {
  rating: number
  category: 'general' | 'experience' | 'paiement' | 'materiel' | 'support'
  comment: string
  contact_email: string
  contact_phone: string
}

const CATEGORIES = [
  { value: 'general', label: 'Général' },
  { value: 'experience', label: 'Expérience de jeu' },
  { value: 'paiement', label: 'Paiement' },
  { value: 'materiel', label: 'Matériel' },
  { value: 'support', label: 'Support' },
]

const STARS = [1, 2, 3, 4, 5]

function CompositionIcon({ item }: { item: string }) {
  const lower = item.toLowerCase()
  if (lower.includes('tv') || lower.includes('pouces')) return <Tv className="h-4 w-4" />
  if (lower.includes('vr') || lower.includes('casque')) return <Headphones className="h-4 w-4" />
  if (lower.includes('console') || lower.includes('ps') || lower.includes('xbox'))
    return <Gamepad2 className="h-4 w-4" />
  if (lower.includes('manette')) return <Joystick className="h-4 w-4" />
  return <Monitor className="h-4 w-4" />
}

function formatDuration(min: number): string {
  if (min < 60) return `${min} min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m === 0 ? `${h}h` : `${h}h${m}`
}

export function StationCheckoutPage() {
  const { stationCode = '' } = useParams()
  const [data, setData] = useState<StationDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [savingOfferId, setSavingOfferId] = useState<number | null>(null)
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')

  const [feedbackForm, setFeedbackForm] = useState<FeedbackForm>({
    rating: 5,
    category: 'general',
    comment: '',
    contact_email: '',
    contact_phone: '',
  })
  const [feedbackDone, setFeedbackDone] = useState(false)
  const [feedbackSaving, setFeedbackSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    void apiGet<StationDetail>(`/public/stations/${encodeURIComponent(stationCode)}`)
      .then((res) => {
        if (!cancelled) setData(res)
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : 'Station introuvable')
      })
    return () => {
      cancelled = true
    }
  }, [stationCode])

  const submit = async (ev: FormEvent, offerId: number, extend: boolean) => {
    ev.preventDefault()
    try {
      setSavingOfferId(offerId)
      setErr(null)
      await postFormNavigate(extend ? '/extend/checkout' : '/checkout', {
        station_code: stationCode,
        offer_id: String(offerId),
        email,
        phone,
        connect: '0',
      })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur lors du paiement')
      setSavingOfferId(null)
    }
  }

  const submitFeedback = async (ev: FormEvent) => {
    ev.preventDefault()
    try {
      setFeedbackSaving(true)
      await apiPostJson<{ ok: boolean }>('/public/feedback', {
        station_code: stationCode,
        rating: feedbackForm.rating,
        category: feedbackForm.category,
        comment: feedbackForm.comment || null,
        contact_email: feedbackForm.contact_email || null,
        contact_phone: feedbackForm.contact_phone || null,
      })
      setFeedbackDone(true)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur feedback')
    } finally {
      setFeedbackSaving(false)
    }
  }

  if (err && !data) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="glass-panel rounded-3xl border border-red-500/30 p-8 text-center max-w-md w-full">
          <p className="font-display text-xl font-bold text-red-300">Station introuvable</p>
          <p className="mt-2 text-sm text-cp-muted">{err}</p>
          <Link to="/" className="mt-6 inline-flex items-center gap-2 text-cp-cyan hover:underline">
            <ArrowLeft className="h-4 w-4" />
            Retour à l'accueil
          </Link>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent to-cp-vr">
          <Gamepad2 className="h-8 w-8 text-white" />
        </div>
        <p className="text-cp-muted">Chargement de la station…</p>
      </div>
    )
  }

  const st = data.station
  const hasOffers = st.offers.length > 0

  return (
    <div className="relative min-h-screen">
      {/* Background ambient */}
      <div className="pointer-events-none fixed inset-0 grid-bg opacity-30" />
      <div className="pointer-events-none fixed inset-0 noise-overlay" />

      <div className="relative mx-auto max-w-2xl px-4 py-8 md:px-6">
        {/* Back link */}
        <Link
          to="/"
          className="mb-6 inline-flex items-center gap-2 text-sm text-cp-muted transition hover:text-cp-text"
        >
          <ArrowLeft className="h-4 w-4" />
          Retour à l'accueil
        </Link>

        {/* Station header */}
        <div className="mb-6 glass-panel rounded-3xl border border-white/10 p-6 animate-fadeIn">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-cp-accent to-cp-vr shadow-lg">
              <Gamepad2 className="h-7 w-7 text-white" />
            </div>
            <div className="flex-1">
              <p className="text-xs font-medium uppercase tracking-wider text-cp-muted">
                Station · {st.code}
              </p>
              <h1 className="font-display mt-1 text-2xl font-bold">
                {st.name}
              </h1>
              {st.has_active_session && (
                <div className="mt-2 flex items-center gap-2 rounded-xl bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-300 w-fit">
                  <Timer className="h-3.5 w-3.5" />
                  Session en cours sur cette station
                </div>
              )}
            </div>
          </div>

          {/* Composition badges */}
          {st.composition.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {st.composition.map((item) => (
                <span
                  key={item}
                  className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-cp-muted"
                >
                  <CompositionIcon item={item} />
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>

        {err && (
          <div className="mb-4 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {err}
          </div>
        )}

        {/* Customer info (minimal) */}
        <div className="mb-6 glass-panel rounded-3xl border border-white/5 p-5 animate-fadeIn stagger-1">
          <p className="mb-4 text-sm font-semibold text-cp-text">
            <Phone className="inline h-4 w-4 mr-2 text-cp-muted" />
            Vos informations (optionnel)
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition focus:border-cp-cyan/50 focus:outline-none focus:ring-2 focus:ring-cp-cyan/10"
              placeholder="Téléphone"
            />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition focus:border-cp-cyan/50 focus:outline-none focus:ring-2 focus:ring-cp-cyan/10"
              placeholder="Email"
            />
          </div>
        </div>

        {/* Offers — main section */}
        {hasOffers ? (
          <>
            {!st.has_active_session && (
              <div className="mb-6 animate-fadeIn stagger-2">
                <h2 className="mb-4 font-display text-lg font-bold">
                  <Zap className="inline h-5 w-5 mr-2 text-cp-cyan" />
                  Démarrer une session
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {st.offers.map((offer, i) => (
                    <form
                      key={offer.id}
                      onSubmit={(e) => void submit(e, offer.id, false)}
                      className={`glass-panel group relative overflow-hidden rounded-2xl border p-5 transition cursor-pointer hover:border-cp-cyan/40 animate-fadeIn ${
                        savingOfferId === offer.id
                          ? 'border-cp-cyan/40 opacity-80'
                          : 'border-white/10'
                      }`}
                      style={{ animationDelay: `${0.1 + i * 0.05}s` }}
                    >
                      {/* Glow on hover */}
                      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-cp-cyan/10 opacity-0 blur-2xl transition-opacity group-hover:opacity-100" />

                      <div className="relative">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-display text-lg font-bold">
                            {formatDuration(offer.duration_minutes)}
                          </p>
                          <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-cp-muted">
                            {offer.provider}
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs text-cp-muted">{offer.name}</p>
                        <p className="mt-3 font-display text-2xl font-extrabold text-cp-text">
                          {offer.price_xof.toLocaleString('fr-FR')}
                          <span className="ml-1 text-base font-normal text-cp-muted">XOF</span>
                        </p>
                        <Button
                          type="submit"
                          className="mt-4 w-full"
                          disabled={savingOfferId === offer.id}
                        >
                          {savingOfferId === offer.id ? (
                            <span className="flex items-center gap-2 justify-center">
                              <div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                              Redirection…
                            </span>
                          ) : (
                            'Payer et jouer'
                          )}
                        </Button>
                      </div>
                    </form>
                  ))}
                </div>
              </div>
            )}

            {/* Extend session */}
            {st.has_active_session && (
              <div className="mb-6 animate-fadeIn stagger-2">
                <h2 className="mb-4 font-display text-lg font-bold">
                  <Timer className="inline h-5 w-5 mr-2 text-amber-400" />
                  Ajouter du temps à la session
                </h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {st.offers.map((offer, i) => (
                    <form
                      key={`ext-${offer.id}`}
                      onSubmit={(e) => void submit(e, offer.id, true)}
                      className="glass-panel group relative overflow-hidden rounded-2xl border border-amber-500/20 p-5 transition hover:border-amber-500/40 animate-fadeIn"
                      style={{ animationDelay: `${0.1 + i * 0.05}s` }}
                    >
                      <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-amber-500/10 opacity-0 blur-2xl transition-opacity group-hover:opacity-100" />
                      <div className="relative">
                        <p className="font-display text-lg font-bold text-amber-300">
                          + {formatDuration(offer.duration_minutes)}
                        </p>
                        <p className="mt-0.5 text-xs text-cp-muted">{offer.name}</p>
                        <p className="mt-3 font-display text-2xl font-extrabold">
                          {offer.price_xof.toLocaleString('fr-FR')}
                          <span className="ml-1 text-base font-normal text-cp-muted">XOF</span>
                        </p>
                        <Button
                          type="submit"
                          variant="secondary"
                          className="mt-4 w-full"
                          disabled={savingOfferId === offer.id}
                        >
                          {savingOfferId === offer.id ? 'Redirection…' : 'Ajouter du temps'}
                        </Button>
                      </div>
                    </form>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="mb-6 glass-panel flex flex-col items-center justify-center rounded-3xl border border-white/5 py-12 text-center animate-fadeIn">
            <Clock className="mb-4 h-10 w-10 text-cp-muted/50" />
            <p className="font-semibold text-cp-text">Aucune offre disponible</p>
            <p className="mt-2 max-w-xs text-sm text-cp-muted">
              Les offres ne sont pas encore configurées pour cette station. Revenez plus tard.
            </p>
          </div>
        )}

        {/* Feedback */}
        <div className="mb-8 glass-panel rounded-3xl border border-white/5 p-6 animate-fadeIn stagger-3">
          <div className="mb-4 flex items-center gap-2">
            <Star className="h-5 w-5 text-cp-amber" />
            <h2 className="font-display text-lg font-bold">Votre avis</h2>
          </div>

          {feedbackDone ? (
            <div className="flex items-center gap-3 rounded-2xl bg-emerald-500/10 px-4 py-3 text-emerald-300">
              <CheckCircle2 className="h-5 w-5 shrink-0" />
              <p className="text-sm font-medium">Merci pour votre avis !</p>
            </div>
          ) : (
            <form onSubmit={submitFeedback} className="space-y-4">
              {/* Star rating */}
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-cp-muted">Note</p>
                <div className="flex gap-2">
                  {STARS.map((star) => (
                    <button
                      key={star}
                      type="button"
                      onClick={() => setFeedbackForm((f) => ({ ...f, rating: star }))}
                      className={`h-10 w-10 rounded-xl border transition ${
                        feedbackForm.rating >= star
                          ? 'border-cp-amber/50 bg-cp-amber/15 text-cp-amber'
                          : 'border-white/10 bg-white/5 text-cp-muted hover:border-white/20'
                      }`}
                    >
                      <Star
                        className="h-5 w-5 mx-auto"
                        fill={feedbackForm.rating >= star ? 'currentColor' : 'none'}
                      />
                    </button>
                  ))}
                </div>
              </div>

              {/* Category */}
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-cp-muted">Catégorie</p>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((cat) => (
                    <button
                      key={cat.value}
                      type="button"
                      onClick={() =>
                        setFeedbackForm((f) => ({
                          ...f,
                          category: cat.value as FeedbackForm['category'],
                        }))
                      }
                      className={`rounded-full border px-3 py-1.5 text-xs transition ${
                        feedbackForm.category === cat.value
                          ? 'border-cp-cyan/40 bg-cp-cyan/10 text-cp-cyan'
                          : 'border-white/10 bg-white/5 text-cp-muted hover:border-white/20'
                      }`}
                    >
                      {cat.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Comment */}
              <div>
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-cp-muted">
                  Commentaire
                </p>
                <textarea
                  value={feedbackForm.comment}
                  onChange={(e) => setFeedbackForm((f) => ({ ...f, comment: e.target.value }))}
                  rows={3}
                  placeholder="Dites-nous ce que vous avez pensé de votre expérience…"
                  className="w-full rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2.5 text-sm text-cp-text placeholder:text-cp-muted/60 transition focus:border-cp-cyan/50 focus:outline-none resize-none"
                />
              </div>

              <Button type="submit" variant="secondary" disabled={feedbackSaving} className="w-full">
                {feedbackSaving ? (
                  <span className="flex items-center gap-2 justify-center">
                    <div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                    Envoi…
                  </span>
                ) : (
                  <span className="flex items-center gap-2 justify-center">
                    <Send className="h-4 w-4" />
                    Envoyer mon avis
                  </span>
                )}
              </Button>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="text-center text-xs text-cp-muted pb-4">
          <Link to="/" className="hover:text-cp-cyan transition">ControlPlay</Link>
          {' · '}
          Réseau de salles de gaming
        </div>
      </div>
    </div>
  )
}
