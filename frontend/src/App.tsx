import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { MarketingLayout } from './layouts/MarketingLayout'
import { AdminLayout } from './layouts/AdminLayout'
import { SuperAdminLayout } from './layouts/SuperAdminLayout'
import { HomePage } from './pages/marketing/HomePage'
import { LocationPage } from './pages/marketing/LocationPage'
import { BoutiquePage } from './pages/marketing/BoutiquePage'
import { BoutiqueCheckoutPage } from './pages/marketing/BoutiqueCheckoutPage'
import { LocationReservationPage } from './pages/marketing/LocationReservationPage'
import { CartePage } from './pages/marketing/CartePage'
import { JeuxPage } from './pages/marketing/JeuxPage'
import { StationCheckoutPage } from './pages/marketing/StationCheckoutPage'
import { Login } from './pages/Login'
import { AdminDashboard } from './pages/admin/Dashboard'
import { StationsDashboard } from './pages/admin/StationsDashboard'
import { Salles } from './pages/admin/Salles'
import { Stations } from './pages/admin/Stations'
import { Offers } from './pages/admin/Offers'
import { Sessions } from './pages/admin/Sessions'
import { MesUtilisateurs } from './pages/admin/MesUtilisateurs'
import { ManualSession } from './pages/admin/ManualSession'
import { FeedbackAdminPage } from './pages/admin/FeedbackAdminPage'
import { RentalPlans } from './pages/admin/RentalPlans'
import { RentalConsoles } from './pages/admin/RentalConsoles'
import { RentalGames } from './pages/admin/RentalGames'
import { BoutiqueProduits } from './pages/admin/BoutiqueProduits'
import { SuperHome } from './pages/super/SuperHome'
import { SuperUsers } from './pages/super/SuperUsers'
import { SuperUserRoles } from './pages/super/SuperUserRoles'
import { SuperProviders } from './pages/super/SuperProviders'
import { SalleOffers } from './pages/admin/SalleOffers'
import { SalleUsers } from './pages/admin/SalleUsers'
import { StationOffers } from './pages/admin/StationOffers'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MarketingLayout />}>
          <Route index element={<HomePage />} />
          <Route path="location" element={<LocationPage />} />
          <Route path="location/reserver" element={<LocationReservationPage />} />
          <Route path="boutique" element={<BoutiquePage />} />
          <Route path="boutique/commande" element={<BoutiqueCheckoutPage />} />
          <Route path="carte" element={<CartePage />} />
          <Route path="jeux" element={<JeuxPage />} />
          <Route path="s/:stationCode" element={<StationCheckoutPage />} />
        </Route>

        <Route path="/login" element={<Login />} />

        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboard />} />
          <Route path="dashboard" element={<StationsDashboard />} />
          <Route path="salles" element={<Salles />} />
          <Route path="salles/:salleId/offers" element={<SalleOffers />} />
          <Route path="salles/:salleId/users" element={<SalleUsers />} />
          <Route path="stations" element={<Stations />} />
          <Route path="stations/:stationId/offers" element={<StationOffers />} />
          <Route path="offers" element={<Offers />} />
          <Route path="rental-plans" element={<RentalPlans />} />
          <Route path="rental-consoles" element={<RentalConsoles />} />
          <Route path="rental-games" element={<RentalGames />} />
          <Route path="boutique-produits" element={<BoutiqueProduits />} />
          <Route path="sessions" element={<Sessions />} />
          <Route path="feedback" element={<FeedbackAdminPage />} />
          <Route path="mes-utilisateurs" element={<MesUtilisateurs />} />
          <Route path="manual-session" element={<ManualSession />} />
        </Route>

        <Route path="/super-admin" element={<SuperAdminLayout />}>
          <Route index element={<SuperHome />} />
          <Route path="users" element={<SuperUsers />} />
          <Route path="users/:userId/roles" element={<SuperUserRoles />} />
          <Route path="providers" element={<SuperProviders />} />
        </Route>

        <Route
          path="*"
          element={
            <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-cp-bg px-6 text-center text-cp-text">
              <p className="font-display text-lg font-semibold">Page introuvable</p>
              <p className="max-w-md text-sm text-cp-muted">
                Cette page n'existe pas. Utilisez le menu principal pour revenir vers la vitrine ou
                l'administration.
              </p>
              <Link to="/" className="text-cp-cyan hover:underline">
                Retour à l’accueil
              </Link>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
