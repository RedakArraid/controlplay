import { type FormEvent, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { apiGet, postFormNavigate } from '../../lib/api'

type Product = {
  id: number
  name: string
  description: string | null
  price_xof: number
  provider: string
}

type Resp = { products: Product[] }

export function BoutiqueCheckoutPage() {
  const [params] = useSearchParams()
  const prePid = params.get('produit')

  const [data, setData] = useState<Resp | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [productId, setProductId] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [connect, setConnect] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let c = false
    ;(async () => {
      try {
        const d = await apiGet<Resp>('/public/shop-products')
        if (c) return
        setData(d)
        const list = d.products ?? []
        if (list.length) {
          const pre = prePid ? list.find((p) => String(p.id) === prePid) : null
          setProductId(String((pre ?? list[0]).id))
        }
      } catch (e) {
        if (!c) setErr(e instanceof Error ? e.message : 'Erreur catalogue')
      }
    })()
    return () => {
      c = true
    }
  }, [prePid])

  const submit = async (ev: FormEvent) => {
    ev.preventDefault()
    setErr(null)
    if (!productId) {
      setErr('Choisissez un produit.')
      return
    }
    if (connect && !phone.trim()) {
      setErr('Numéro de téléphone obligatoire si vous liez un compte.')
      return
    }
    try {
      setSaving(true)
      await postFormNavigate('/shop/checkout', {
        shop_product_id: productId,
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

  const products = data?.products ?? []
  const selected = products.find((p) => String(p.id) === productId)

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 md:px-6 md:py-16">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cp-amber">Boutique</p>
      <h1 className="font-display mt-2 text-3xl font-extrabold tracking-tight md:text-4xl">
        Commander un <span className="text-gradient-brand">article</span>
      </h1>
      <p className="mt-4 text-sm text-cp-muted">
        Articles gérés en admin plateforme. Puis confirmation par Paystack / CinetPay selon
        configuration du serveur — comme la location ou le temps de jeu.
      </p>

      <div className="mt-6 text-sm">
        <Link to="/boutique" className="text-cp-teal hover:underline">
          ← Catalogue
        </Link>
      </div>

      {!data && !err ? (
        <p className="mt-10 flex items-center gap-2 text-cp-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
        </p>
      ) : null}

      {err ? <p className="mt-8 text-rose-300">{err}</p> : null}

      {data && products.length === 0 ? (
        <p className="mt-10 text-cp-muted">
          Aucun produit catalogue pour le moment. Les administrateurs plateforme peuvent en ajouter
          dans Produits boutique.
        </p>
      ) : null}

      {data && products.length > 0 ? (
        <Card className="mt-10 border-cp-amber/15 bg-cp-amber/[0.04] p-6 md:p-8">
          <form className="space-y-6" onSubmit={submit}>
            <Select
              label="Produit"
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              disabled={saving}
              required
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} — {p.price_xof} XOF
                </option>
              ))}
            </Select>
            {selected?.description ? (
              <p className="text-sm text-cp-muted">{selected.description}</p>
            ) : null}

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={connect}
                onChange={(e) => setConnect(e.target.checked)}
                className="mt-1"
              />
              <span className="text-cp-muted">
                Lier à un téléphone pour le suivi de commande (le numéro devient alors obligatoire).
              </span>
            </label>

            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label={connect ? 'Email' : 'Email (optionnel)'}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                disabled={saving}
              />
              <Input
                label={connect ? 'Téléphone (obligatoire)' : 'Téléphone (optionnel)'}
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
                disabled={saving}
                required={connect}
              />
            </div>

            <Button type="submit" disabled={saving} className="w-full sm:w-auto">
              {saving ? 'Redirection paiement…' : 'Passer au paiement'}
            </Button>
          </form>
        </Card>
      ) : null}
    </div>
  )
}
