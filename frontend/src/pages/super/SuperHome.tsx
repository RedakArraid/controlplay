import { Link, useOutletContext } from 'react-router-dom'
import { Crown, CreditCard, LayoutDashboard, Users } from 'lucide-react'
import { PageHeader } from '../../components/PageHeader'
import { Card } from '../../components/Card'
import type { AdminBootstrap, AuthMe } from '../../types'

type Ctx = { me: AuthMe; boot: AdminBootstrap | null }

export function SuperHome() {
  const { me } = useOutletContext<Ctx>()
  const canUsers =
    me.is_super_admin || me.staff_permissions?.includes('users')
  const canProviders = me.is_super_admin
  const canOps =
    me.is_super_admin || me.staff_permissions?.includes('operations')

  const tiles: {
    to: string
    title: string
    desc: string
    icon: typeof Users
  }[] = []
  if (canUsers) {
    tiles.push({
      to: '/super-admin/users',
      title: 'Utilisateurs globaux',
      desc: 'Comptes et rôles (hors super administrateurs pour l’équipe déléguée).',
      icon: Users,
    })
  }
  if (canProviders) {
    tiles.push({
      to: '/super-admin/providers',
      title: 'Providers PSP',
      desc: 'Paystack & CinetPay — réservé au super administrateur.',
      icon: CreditCard,
    })
  }
  if (canOps) {
    tiles.push({
      to: '/admin/stations',
      title: 'Consoles / stations',
      desc: 'Ajouter et configurer les stations comme dans l’admin.',
      icon: LayoutDashboard,
    })
    tiles.push({
      to: '/admin/offers',
      title: 'Jeux / offres',
      desc: 'Créer les offres de jeu (durée, prix) comme dans l’admin.',
      icon: LayoutDashboard,
    })
    tiles.push({
      to: '/admin/rental-plans',
      title: 'Prix de location',
      desc: 'Gérer les forfaits de location console.',
      icon: LayoutDashboard,
    })
    tiles.push({
      to: '/admin/dashboard',
      title: 'Dashboard stations',
      desc: 'Vue opérationnelle du parc (menu admin).',
      icon: LayoutDashboard,
    })
  }

  return (
    <>
      <PageHeader
        title="Espace plateforme"
        description={
          me.is_super_admin
            ? 'Super administrateur — toutes les options.'
            : 'Équipe ControlPlay — accès limité aux délégations accordées par le super administrateur.'
        }
      />
      <div className="mb-6 flex items-center gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm text-amber-100/90">
        <Crown className="h-5 w-5 shrink-0 text-amber-300" />
        {me.is_super_admin
          ? 'Vous opérez au niveau plateforme : prudence sur les rôles et les paiements.'
          : 'Les réglages PSP (Paystack / CinetPay) ne sont pas accessibles depuis ce profil.'}
      </div>
      {tiles.length === 0 ? (
        <p className="text-cp-muted">
          Aucune tuile disponible. Demandez au super administrateur d’accorder les permissions «
          operations » et/ou « users ».
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {tiles.map((t) => (
            <Link key={t.to} to={t.to}>
              <Card className="h-full transition hover:border-cp-accent/40 hover:bg-white/[0.04]">
                <t.icon className="mb-3 h-8 w-8 text-cp-accent" />
                <h3 className="font-semibold">{t.title}</h3>
                <p className="mt-2 text-sm text-cp-muted">{t.desc}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </>
  )
}
