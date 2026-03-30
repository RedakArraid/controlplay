import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import { Button } from '../../components/ui/Button'
import { apiGet } from '../../lib/api'
import type { AdminBootstrap, AuthMe } from '../../types'

type P = { paystack_enabled: boolean; cinetpay_enabled: boolean }

export function SuperProviders() {
  const { me } = useOutletContext<{ me: AuthMe; boot: AdminBootstrap | null }>()
  const [cfg, setCfg] = useState<P | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!me.is_super_admin) return
    apiGet<P>('/super-admin/providers')
      .then(setCfg)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Erreur'))
  }, [me.is_super_admin])

  if (!me.is_super_admin) {
    return (
      <>
        <PageHeader title="Providers PSP" description="Réservé au super administrateur." />
        <p className="text-cp-muted">
          Les paramètres de paiement (Paystack / CinetPay) ne sont accessibles qu’au super administrateur.
        </p>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Providers de paiement"
        description="Activation Paystack / CinetPay (configuration centrale)."
      />
      {err ? <p className="text-rose-300">{err}</p> : null}
      {!cfg ? (
        <p className="text-cp-muted">Chargement…</p>
      ) : (
        <Card>
          <form method="post" action="/admin/providers" className="space-y-6">
            <input type="hidden" name="redirect_after" value="/super-admin/providers" />
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                name="paystack_enabled"
                value="1"
                defaultChecked={cfg.paystack_enabled}
              />
              Paystack activé
            </label>
            <label className="flex items-center gap-3 text-sm">
              <input
                type="checkbox"
                name="cinetpay_enabled"
                value="1"
                defaultChecked={cfg.cinetpay_enabled}
              />
              CinetPay activé
            </label>
            <p className="text-xs text-cp-muted">
              Si une case est décochée, n’envoyez pas le champ (valeur 0 côté serveur).
            </p>
            <Button type="submit">Enregistrer</Button>
          </form>
        </Card>
      )}
    </>
  )
}
