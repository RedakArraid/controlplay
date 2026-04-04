import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, apiPostJson, postFormNavigate } from '../../lib/api'

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
  }
}

type CheckoutForm = {
  email: string
  phone: string
  connect: boolean
}

type FeedbackForm = {
  rating: number
  category: 'general' | 'experience' | 'paiement' | 'materiel' | 'support'
  comment: string
  contact_email: string
  contact_phone: string
}

export function StationCheckoutPage() {
  const { stationCode = '' } = useParams()
  const [data, setData] = useState<StationDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [savingOfferId, setSavingOfferId] = useState<number | null>(null)
  const [form, setForm] = useState<CheckoutForm>({ email: '', phone: '', connect: false })
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
        if (cancelled) return
        setData(res)
      })
      .catch((e) => {
        if (cancelled) return
        setErr(e instanceof Error ? e.message : 'Erreur')
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
        email: form.email,
        phone: form.phone,
        connect: form.connect ? '1' : '0',
      })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur checkout')
      setSavingOfferId(null)
    }
  }

  const submitFeedback = async (ev: FormEvent) => {
    ev.preventDefault()
    try {
      setFeedbackSaving(true)
      setErr(null)
      await apiPostJson<{ ok: boolean; feedback_id: number }>('/public/feedback', {
        station_code: stationCode,
        rating: feedbackForm.rating,
        category: feedbackForm.category,
        comment: feedbackForm.comment || null,
        contact_email: feedbackForm.contact_email || null,
        contact_phone: feedbackForm.contact_phone || null,
      })
      setFeedbackDone(true)
      setFeedbackForm({
        rating: 5,
        category: 'general',
        comment: '',
        contact_email: '',
        contact_phone: '',
      })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Erreur feedback')
    } finally {
      setFeedbackSaving(false)
    }
  }

  if (err && !data) {
    return (
      <section className="mx-auto max-w-4xl px-4 py-10 md:px-6">
        <p className="text-rose-300">{err}</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="mx-auto max-w-4xl px-4 py-10 md:px-6">
        <p className="text-cp-muted">Chargement…</p>
      </section>
    )
  }

  const st = data.station

  return (
    <section className="mx-auto max-w-5xl px-4 py-10 md:px-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-cp-muted">Station</p>
          <h1 className="font-display text-3xl font-bold">{st.name}</h1>
          <p className="text-sm text-cp-muted">Code: {st.code}</p>
        </div>
        <Link className="text-cp-cyan hover:underline" to="/">
          Retour accueil
        </Link>
      </div>

      {st.composition.length ? (
        <div className="mb-6 flex flex-wrap gap-2">
          {st.composition.map((item) => (
            <span key={item} className="rounded-full border border-cp-border px-3 py-1 text-xs text-cp-muted">
              {item}
            </span>
          ))}
        </div>
      ) : null}

      {err ? <p className="mb-4 text-rose-300">{err}</p> : null}

      <Card className="mb-6">
        <h2 className="mb-3 font-semibold">Informations client</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Email (optionnel)"
          />
          <input
            value={form.phone}
            onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Téléphone (optionnel)"
          />
          <label className="flex items-center gap-2 text-sm text-cp-muted">
            <input
              type="checkbox"
              checked={form.connect}
              onChange={(e) => setForm((f) => ({ ...f, connect: e.target.checked }))}
            />
            Lier un compte (téléphone requis)
          </label>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {st.offers.map((offer) => (
          <Card key={offer.id}>
            <p className="text-xs text-cp-muted">{offer.provider}</p>
            <h3 className="mt-1 text-lg font-semibold">{offer.name}</h3>
            <p className="mt-1 text-sm text-cp-muted">
              {offer.duration_minutes} min · {offer.price_xof} XOF
            </p>
            <form className="mt-4" onSubmit={(e) => void submit(e, offer.id, false)}>
              <Button type="submit" disabled={savingOfferId === offer.id}>
                {savingOfferId === offer.id ? 'Redirection…' : 'Payer'}
              </Button>
            </form>
          </Card>
        ))}
      </div>

      {st.has_active_session ? (
        <div className="mt-8">
          <h2 className="mb-3 font-semibold">Session en cours - Ajouter du temps</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {st.offers.map((offer) => (
              <Card key={`ext-${offer.id}`}>
                <h3 className="text-lg font-semibold">+ {offer.duration_minutes} min</h3>
                <p className="mt-1 text-sm text-cp-muted">
                  {offer.name} · {offer.price_xof} XOF
                </p>
                <form className="mt-4" onSubmit={(e) => void submit(e, offer.id, true)}>
                  <Button type="submit" variant="secondary" disabled={savingOfferId === offer.id}>
                    {savingOfferId === offer.id ? 'Redirection…' : 'Ajouter du temps'}
                  </Button>
                </form>
              </Card>
            ))}
          </div>
        </div>
      ) : null}

      <Card className="mt-8">
        <h2 className="mb-2 font-semibold">Votre feedback</h2>
        <p className="mb-3 text-sm text-cp-muted">
          Dites-nous ce qui s’est bien passé ou ce qu’on doit améliorer.
        </p>
        {feedbackDone ? <p className="mb-3 text-emerald-300">Merci, votre avis est enregistré.</p> : null}
        <form onSubmit={submitFeedback} className="grid gap-3 md:grid-cols-2">
          <select
            value={String(feedbackForm.rating)}
            onChange={(e) => setFeedbackForm((f) => ({ ...f, rating: Number(e.target.value) }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="5">5 - Excellent</option>
            <option value="4">4 - Bien</option>
            <option value="3">3 - Moyen</option>
            <option value="2">2 - Décevant</option>
            <option value="1">1 - Mauvais</option>
          </select>
          <select
            value={feedbackForm.category}
            onChange={(e) =>
              setFeedbackForm((f) => ({
                ...f,
                category: e.target.value as FeedbackForm['category'],
              }))
            }
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
          >
            <option value="general">Général</option>
            <option value="experience">Expérience de jeu</option>
            <option value="paiement">Paiement</option>
            <option value="materiel">Matériel</option>
            <option value="support">Support</option>
          </select>
          <textarea
            value={feedbackForm.comment}
            onChange={(e) => setFeedbackForm((f) => ({ ...f, comment: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm md:col-span-2"
            rows={3}
            placeholder="Votre message (optionnel)"
          />
          <input
            type="email"
            value={feedbackForm.contact_email}
            onChange={(e) => setFeedbackForm((f) => ({ ...f, contact_email: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Email de contact (optionnel)"
          />
          <input
            value={feedbackForm.contact_phone}
            onChange={(e) => setFeedbackForm((f) => ({ ...f, contact_phone: e.target.value }))}
            className="rounded-xl border border-cp-border bg-cp-bg/60 px-3 py-2 text-sm"
            placeholder="Téléphone de contact (optionnel)"
          />
          <div className="md:col-span-2">
            <Button type="submit" disabled={feedbackSaving}>
              {feedbackSaving ? 'Envoi…' : 'Envoyer mon avis'}
            </Button>
          </div>
        </form>
      </Card>
    </section>
  )
}
