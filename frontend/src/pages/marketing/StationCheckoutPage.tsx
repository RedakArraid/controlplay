import { FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet, postFormNavigate } from '../../lib/api'

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

export function StationCheckoutPage() {
  const { stationCode = '' } = useParams()
  const [data, setData] = useState<StationDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [savingOfferId, setSavingOfferId] = useState<number | null>(null)
  const [form, setForm] = useState<CheckoutForm>({ email: '', phone: '', connect: false })

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
    </section>
  )
}
