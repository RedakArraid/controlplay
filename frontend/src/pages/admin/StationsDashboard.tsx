import { AdminDashboard } from './Dashboard'

/** Route /admin/dashboard — libellé aligné sur le menu. */
export function StationsDashboard() {
  return (
    <AdminDashboard
      title="Dashboard stations"
      description="Même synthèse que le tableau de bord : état live du parc."
    />
  )
}
